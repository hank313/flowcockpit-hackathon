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
        val components = (0 until array.length()).flatMap { i ->
            array.optJSONObject(i)?.let(::parseComponent).orEmpty()
        }
        return UiDescription(
            components = components,
            clarificationNeeded = payload.optStringOrNull("clarification_needed"),
        )
    }

    // D 用 "component" 欄位,README 共用規範用 "type"
    private fun parseComponent(obj: JSONObject): List<UiComponent> =
        if (obj.has("component")) parseDComponent(obj) else listOf(parseSpecComponent(obj))

    private fun parseDComponent(obj: JSONObject): List<UiComponent> {
        val type = obj.optString("component")
        val data = obj.optJSONObject("data") ?: JSONObject()
        return when (type) {
            "filter_controls" -> {
                val array = data.optJSONArray("filters") ?: JSONArray()
                val filters = linkedMapOf<String, Any?>()
                val labels = mutableMapOf<String, String>()
                for (i in 0 until array.length()) {
                    val f = array.optJSONObject(i) ?: continue
                    val key = f.optString("id")
                    if (key.isEmpty()) continue
                    val value = f.opt("value").takeUnless { it == JSONObject.NULL }
                    // STEPPER 的 value 是 "<= 10 分鐘" 這類字串,取出數字才能調整
                    filters[key] = if (value is String) firstNumber(value) ?: value else value
                    f.optStringOrNull("label")?.let { labels[key] = it }
                }
                listOf(UiComponent.ConditionControl(type, filters, labels))
            }

            "candidate_list" -> {
                val selectedId = data.optStringOrNull("selected_id")
                val items = data.optJSONArray("items") ?: JSONArray()
                (0 until items.length()).mapNotNull { i ->
                    val item = items.optJSONObject(i) ?: return@mapNotNull null
                    val id = item.optStringOrNull("id") ?: return@mapNotNull null
                    UiComponent.CandidateCard(
                        id = "card_$id",
                        candidateId = id,
                        name = item.optStringOrNull("name"),
                        attributes = emptyMap(),
                        selected = id == selectedId,
                        tags = listOfNotNull(
                            item.optStringOrNull("drive_distance_desc"),
                            item.optStringOrNull("drive_eta_desc"),
                        ) + item.optJSONArray("tags").toStringList(),
                    )
                }
            }

            "comparison_panel" -> {
                if (!data.optBoolean("visible", true)) return emptyList()
                listOf(
                    UiComponent.CompareConfirmPanel(
                        id = type,
                        candidateIds = listOfNotNull(data.optStringOrNull("selected_id")),
                        comparisonText = data.optStringOrNull("cloud_enhanced_text"),
                        confirmEnabled = data.optString("status") != "CONFIRMED",
                    )
                )
            }

            else -> listOf(UiComponent.Unsupported(type, type))
        }
    }

    private fun parseSpecComponent(obj: JSONObject): UiComponent {
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

    private fun JSONArray?.toStringList(): List<String> =
        if (this == null) emptyList() else (0 until length()).mapNotNull { optStringOrNull(it) }

    private val NUMBER = Regex("""\d+(\.\d+)?""")

    private fun firstNumber(text: String): Number? =
        NUMBER.find(text)?.value?.let { it.toIntOrNull() ?: it.toDouble() }
}
