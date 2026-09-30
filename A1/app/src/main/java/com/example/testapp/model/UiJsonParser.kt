package com.example.testapp.model

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/** 容錯解析:欄位缺漏時給 null(畫面顯示「未知」),不丟例外 */
object UiJsonParser {

    fun parseEnvelope(json: String): Envelope? = try {
        val obj = JSONObject(json)
        Envelope(
            taskId = obj.optString("task_id"),
            version = obj.optInt("version", -1),
            type = obj.optString("type"),
            payload = obj.optJSONObject("payload") ?: JSONObject(),
        )
    } catch (e: JSONException) {
        null
    }

    fun parseUiDescription(payload: JSONObject): UiDescription {
        val array = payload.optJSONArray("components") ?: JSONArray()
        val components = (0 until array.length()).mapNotNull { i ->
            array.optJSONObject(i)?.let(::parseComponent)
        }
        return UiDescription(
            components = components,
            clarificationNeeded = payload.optStringOrNull("clarification_needed"),
        )
    }

    private fun parseComponent(obj: JSONObject): UiComponent {
        val type = obj.optString("type")
        val id = obj.optString("id").ifEmpty { "${type}_${obj.hashCode()}" }
        val data = obj.optJSONObject("data") ?: JSONObject()
        return when (type) {
            "condition_control" -> UiComponent.ConditionControl(
                id = id,
                filters = data.optJSONObject("filters").toMap(),
            )

            "candidate_card" -> UiComponent.CandidateCard(
                id = id,
                candidateId = data.optString("candidate_id", id),
                name = data.optStringOrNull("name"),
                attributes = data.optJSONObject("attributes").toMap(),
                selected = data.optBoolean("selected", false),
            )

            "compare_confirm_panel" -> {
                val ids = data.optJSONArray("candidate_ids") ?: JSONArray()
                UiComponent.CompareConfirmPanel(
                    id = id,
                    candidateIds = (0 until ids.length()).mapNotNull { ids.optStringOrNull(it) },
                    comparisonText = data.optStringOrNull("comparison_text"),
                    confirmEnabled = data.optBoolean("confirm_enabled", false),
                )
            }

            else -> UiComponent.Unsupported(id, type)
        }
    }

    private fun JSONObject?.toMap(): Map<String, Any?> {
        if (this == null) return emptyMap()
        return keys().asSequence().associateWith { key ->
            opt(key).takeUnless { it == JSONObject.NULL }
        }
    }

    private fun JSONObject.optStringOrNull(key: String): String? =
        if (isNull(key)) null else optString(key).ifEmpty { null }

    private fun JSONArray.optStringOrNull(index: Int): String? =
        if (isNull(index)) null else optString(index).ifEmpty { null }
}
