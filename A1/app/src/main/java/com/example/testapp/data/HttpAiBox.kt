package com.example.testapp.data

import android.content.Context
import com.example.testapp.model.UserAction
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * 連線 D 後端(FastAPI):
 * - 按住麥克風錄音,放開後 POST wav 到 /api/audio
 * - UI JSON 由 WebSocket /ws 推回來,同時另存 filesDir/d_output.json
 * - 連不上後端時,讀 d_output.json 當離線備援
 *
 * [host] 例如 "10.0.2.2:8000"(Android 模擬器連本機)或 AI Box 的區網 IP
 */
class HttpAiBox(
    private val context: Context,
    private val scope: CoroutineScope,
    private val host: String,
) : AiBoxGateway {

    // WebSocket 不設讀取逾時,靠 ping 偵測斷線;上傳要等 D→BC→Whisper→LLM,逾時放長
    private val wsClient = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private val httpClient = OkHttpClient.Builder()
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    private val recorder = WavRecorder(File(context.cacheDir, "voice.wav"))
    private val dOutput = File(context.filesDir, "d_output.json")

    private val _messages = MutableSharedFlow<String>(extraBufferCapacity = 8)
    override val messages: Flow<String> = _messages.asSharedFlow()

    private var socket: WebSocket? = null
    @Volatile private var taskId = DEFAULT_TASK_ID
    @Volatile private var version = 1
    @Volatile private var gotLive = false
    private var fallbackSent = false

    init {
        connect()
    }

    private fun connect() {
        socket = wsClient.newWebSocket(
            Request.Builder().url("ws://$host/ws").build(),
            object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    gotLive = true
                    runCatching { JSONObject(text) }.getOrNull()?.let {
                        taskId = it.optString("task_id", taskId)
                        version = it.optInt("version", version)
                    }
                    runCatching { dOutput.writeText(text) }
                    _messages.tryEmit(text)
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    if (!gotLive && !fallbackSent) {
                        fallbackSent = true
                        emitFallback()
                    }
                    reconnect()
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    reconnect()
                }
            },
        )
    }

    private fun reconnect() {
        scope.launch {
            delay(2_000)
            connect()
        }
    }

    /** 先讀 App 上次存的 d_output.json,沒有才讀 assets 內建的 */
    private fun emitFallback() {
        val text = runCatching {
            if (dOutput.exists()) dOutput.readText()
            else context.assets.open("ui/d_output.json").bufferedReader().use { it.readText() }
        }.getOrNull() ?: return
        _messages.tryEmit(text)
    }

    override fun startVoiceInput() {
        recorder.start(scope)
    }

    override fun stopVoiceInput() {
        scope.launch {
            val wav = recorder.stop() ?: return@launch
            withContext(Dispatchers.IO) {
                val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                    .addFormDataPart("file", "voice.wav", wav.asRequestBody("audio/wav".toMediaType()))
                    .addFormDataPart("task_id", taskId)
                    .build()
                // 畫面由 WebSocket 推回來,這裡只負責送出
                runCatching {
                    httpClient.newCall(
                        Request.Builder().url("http://$host/api/audio").post(body).build(),
                    ).execute().close()
                }
            }
        }
    }

    override fun sendAction(action: UserAction) {
        val msg = JSONObject()
            .put("task_id", taskId)
            .put("version", version)
            .put("type", "TOUCH_ACTION")
            .put("payload", action.toPayload())
        socket?.send(msg.toString())
    }

    private companion object {
        const val DEFAULT_TASK_ID = "demo_task_001"
    }
}
