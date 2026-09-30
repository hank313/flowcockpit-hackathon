package com.example.testapp.model

import org.json.JSONObject

/** WebSocket 外層包裝:{"task_id","version","type","payload"} */
data class Envelope(
    val taskId: String,
    val version: Int,
    val type: String,
    val payload: JSONObject,
)

/** D → A1 的生成式 UI 描述 */
data class UiDescription(
    val components: List<UiComponent>,
    val clarificationNeeded: String?,
)

sealed interface UiComponent {
    val id: String

    data class ConditionControl(
        override val id: String,
        val filters: Map<String, Any?>,
    ) : UiComponent

    data class CandidateCard(
        override val id: String,
        val candidateId: String,
        val name: String?,
        val attributes: Map<String, Any?>,
        val selected: Boolean,
    ) : UiComponent

    data class CompareConfirmPanel(
        override val id: String,
        val candidateIds: List<String>,
        val comparisonText: String?,
        val confirmEnabled: Boolean,
    ) : UiComponent

    /** 未知的 type,渲染時略過,避免 crash */
    data class Unsupported(override val id: String, val type: String) : UiComponent
}

/** A1 元件產生的使用者操作,由 A2 包成 user_action 送給 AI Box */
sealed interface UserAction {
    fun toPayload(): JSONObject

    data class SelectCandidate(val candidateId: String) : UserAction {
        override fun toPayload(): JSONObject = JSONObject()
            .put("action", "select_candidate")
            .put("candidate_id", candidateId)
    }

    // update_condition / confirm 的 payload 欄位尚未在規範中定案,需與 D 對齊
    data class UpdateCondition(val key: String, val value: Any?) : UserAction {
        override fun toPayload(): JSONObject = JSONObject()
            .put("action", "update_condition")
            .put("key", key)
            .put("value", value ?: JSONObject.NULL)
    }

    data class Confirm(val candidateId: String) : UserAction {
        override fun toPayload(): JSONObject = JSONObject()
            .put("action", "confirm")
            .put("candidate_id", candidateId)
    }
}
