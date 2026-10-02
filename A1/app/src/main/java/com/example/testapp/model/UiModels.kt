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
        val labels: Map<String, String> = emptyMap(),
    ) : UiComponent

    data class CandidateCard(
        override val id: String,
        val candidateId: String,
        val name: String?,
        val attributes: Map<String, Any?>,
        val selected: Boolean,
        val tags: List<String> = emptyList(),
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

/** A1 元件產生的使用者操作,由 A2 包成 TOUCH_ACTION 送給 D */
sealed interface UserAction {
    fun toPayload(): JSONObject

    data class SelectCandidate(val candidateId: String) : UserAction {
        override fun toPayload(): JSONObject = JSONObject()
            .put("action", "SELECT_CANDIDATE")
            .put("candidate_id", candidateIdJson(candidateId))
    }

    data class UpdateCondition(val key: String, val value: Any?) : UserAction {
        override fun toPayload(): JSONObject = JSONObject()
            .put("action", "UPDATE_FILTER")
            .put("filters", JSONObject().put(key, value ?: JSONObject.NULL))
    }

    data class Confirm(val candidateId: String) : UserAction {
        override fun toPayload(): JSONObject = JSONObject()
            .put("action", "CONFIRM_DESTINATION")
            .put("candidate_id", candidateIdJson(candidateId))
    }
}

// D 的地點 id 是整數
private fun candidateIdJson(id: String): Any = id.toIntOrNull() ?: id
