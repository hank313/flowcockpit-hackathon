package com.example.testapp.data

import android.content.Context
import com.example.testapp.model.UserAction
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * 從 assets/[dir] 讀取 .json(WebSocket 外層包裝格式)送給畫面。
 * 每次放開麥克風依檔名順序送出下一份,確認後從第一份重來。
 */
class AssetJsonAiBox(
    private val context: Context,
    private val scope: CoroutineScope,
    private val dir: String = "ui",
) : AiBoxGateway {

    private val _messages = MutableSharedFlow<String>(extraBufferCapacity = 8)
    override val messages: Flow<String> = _messages.asSharedFlow()

    private val files: List<String> =
        context.assets.list(dir).orEmpty().filter { it.endsWith(".json") }.sorted()
    private var index = 0

    override fun startVoiceInput() = Unit

    override fun stopVoiceInput() {
        if (files.isEmpty()) return
        val name = files[index++ % files.size]
        scope.launch {
            val json = withContext(Dispatchers.IO) {
                context.assets.open("$dir/$name").bufferedReader().use { it.readText() }
            }
            _messages.emit(json)
        }
    }

    override fun sendAction(action: UserAction) {
        if (action is UserAction.Confirm) index = 0
    }
}
