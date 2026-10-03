package com.example.testapp.ui.screens

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.example.testapp.data.AiBoxGateway
import com.example.testapp.model.UiComponent
import com.example.testapp.model.UiDescription
import com.example.testapp.model.UiJsonParser
import com.example.testapp.model.UserAction
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

enum class MicState { Idle, Listening, Processing }

const val INITIAL_DESTINATION = "國立雲林科技大學"

/** 主畫面狀態;A2 可在此接上真正的 WebSocket gateway 與行駛模式 */
class CockpitController(
    private val gateway: AiBoxGateway,
    private val scope: CoroutineScope,
) {
    var ui by mutableStateOf<UiDescription?>(null)
        private set
    var micState by mutableStateOf(MicState.Idle)
        private set
    var destination by mutableStateOf<String?>(INITIAL_DESTINATION)
        private set

    private var taskId: String? = null
    private var version = -1
    private var processingTimeout: Job? = null

    /** 錄音送出之後才顯示 AI 建議;啟動、收合、確認之後 D 推來的狀態只記錄版本,不顯示 */
    private var awaitingResult = false

    init {
        scope.launch { gateway.messages.collect(::onMessage) }
    }

    fun onMicPressed() {
        micState = MicState.Listening
        gateway.startVoiceInput()
    }

    fun onMicReleased() {
        micState = MicState.Processing
        awaitingResult = true
        gateway.stopVoiceInput()
        processingTimeout?.cancel()
        processingTimeout = scope.launch {
            // D 轉 BC 的逾時是 30 秒,首次辨識還要載入模型,不能比它短
            delay(30_000)
            micState = MicState.Idle
            // 逾時仍沒有結果就不再等待;面板已顯示時要繼續接收觸控操作的回應
            if (ui == null) awaitingResult = false
        }
    }

    fun onAction(action: UserAction) {
        if (action is UserAction.Confirm) {
            destination = ui?.components
                ?.filterIsInstance<UiComponent.CandidateCard>()
                ?.firstOrNull { it.candidateId == action.candidateId }
                ?.name ?: action.candidateId
            ui = null
            awaitingResult = false
            taskId = null
            version = -1
        }
        gateway.sendAction(action)
    }

    fun dismissPanel() {
        ui = null
        awaitingResult = false
    }

    private fun onMessage(json: String) {
        val envelope = UiJsonParser.parseEnvelope(json) ?: return
        if (!envelope.type.equals("ui_update", ignoreCase = true)) return
        // 同一任務中版本較舊(或重複)的訊息一律丟棄
        if (envelope.taskId == taskId && envelope.version <= version) return
        taskId = envelope.taskId
        version = envelope.version
        if (!awaitingResult) return
        ui = UiJsonParser.parseUiDescription(envelope.payload)
        processingTimeout?.cancel()
        if (micState == MicState.Processing) micState = MicState.Idle
    }
}
