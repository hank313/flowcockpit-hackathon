package com.example.testapp.data

import com.example.testapp.model.UserAction
import kotlinx.coroutines.flow.Flow

/** A1 畫面與 AI Box 之間的介面;A2 以 WebSocket 實作取代 [FakeAiBox] */
interface AiBoxGateway {
    /** 收到的 WebSocket 外層包裝 JSON 字串 */
    val messages: Flow<String>

    fun startVoiceInput()
    fun stopVoiceInput()
    fun sendAction(action: UserAction)
}
