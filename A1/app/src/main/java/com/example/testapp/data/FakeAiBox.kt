package com.example.testapp.data

import com.example.testapp.model.UserAction
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/**
 * 假的 AI Box,依定案 JSON 格式回傳 ui_update,供 A1 在沒有後端時開發與展示。
 * 語音輸入依序模擬:找休息地點 → 要更近的 → 聽不懂(觸發澄清)。
 */
class FakeAiBox(private val scope: CoroutineScope) : AiBoxGateway {

    private data class Place(
        val id: String,
        val name: String,
        val indoor: Boolean,
        val hasSeating: Boolean,
        val hasFood: Boolean,
        val driveDistanceM: Int,
        val driveTimeMin: Int,
    )

    private val places = listOf(
        Place("loc_001", "謝孟勳的狗窝", true, true, true, 1200, 8),
        Place("loc_002", "麥當勞-斗六雲林餐廳", true, true, true, 1800, 12),
        Place("loc_003", "河濱公園涼亭", false, true, false, 2500, 5),
        Place("loc_004", "觀景台休息區", false, false, false, 600, 15),
        Place("loc_005", "國道便利商店", true, false, true, 400, 6),
        Place("loc_006", "文創園區 閱讀室", true, true, false, 4500, 10),
        Place("loc_007", "加油站休息室", true, true, false, 300, 3),
        Place("loc_008", "休息站 按摩椅區", true, true, false, 900, 7),
        Place("loc_009", "書店咖啡角", true, true, true, 2200, 9),
        Place("loc_010", "親子餐廳", true, true, true, 2600, 11),
    )

    private val _messages = MutableSharedFlow<String>(extraBufferCapacity = 8)
    override val messages: Flow<String> = _messages.asSharedFlow()

    private var taskSeq = 1
    private var version = 0
    private var voiceTurn = 0
    private val filters = linkedMapOf<String, Any?>()
    private var selectedId: String? = null

    override fun startVoiceInput() = Unit

    override fun stopVoiceInput() {
        scope.launch {
            delay(900)
            when (voiceTurn++ % 3) {
                0 -> {
                    filters.clear()
                    filters["indoor"] = true
                    filters["has_seating"] = true
                    // false 代表不限制,只是讓畫面出現可切換的「有餐飲」條件
                    filters["has_food"] = false
                    filters["max_drive_distance_m"] = 3000
                    emitUi()
                }
                1 -> {
                    filters["max_drive_distance_m"] = 1500
                    emitUi()
                }
                else -> emitUi(clarification = "想找休息地點、加油站,還是用餐的地方?")
            }
        }
    }

    override fun sendAction(action: UserAction) {
        scope.launch {
            delay(200)
            when (action) {
                is UserAction.SelectCandidate ->
                    selectedId = if (selectedId == action.candidateId) null else action.candidateId
                is UserAction.UpdateCondition -> filters[action.key] = action.value
                is UserAction.Confirm -> {
                    taskSeq++
                    version = 0
                    voiceTurn = 0
                    filters.clear()
                    selectedId = null
                    return@launch
                }
            }
            emitUi()
        }
    }

    private fun matchedPlaces(): List<Place> = places.filter { p ->
        (filters["indoor"] as? Boolean)?.let { p.indoor == it } ?: true &&
            (filters["has_seating"] as? Boolean)?.let { !it || p.hasSeating } ?: true &&
            (filters["has_food"] as? Boolean)?.let { !it || p.hasFood } ?: true &&
            p.driveDistanceM <= ((filters["max_drive_distance_m"] as? Number)?.toInt() ?: Int.MAX_VALUE)
    }

    private suspend fun emitUi(clarification: String? = null) {
        val matched = matchedPlaces()
        if (matched.none { it.id == selectedId }) selectedId = null

        val components = JSONArray()
        val filterJson = JSONObject()
        filters.forEach { (k, v) -> filterJson.put(k, v ?: JSONObject.NULL) }
        components.put(component("condition_control", "cond_1", JSONObject().put("filters", filterJson)))

        matched.forEach { p ->
            components.put(
                component(
                    "candidate_card", "card_${p.id}",
                    JSONObject()
                        .put("candidate_id", p.id)
                        .put("name", p.name)
                        .put(
                            "attributes", JSONObject()
                                .put("indoor", p.indoor)
                                .put("has_seating", p.hasSeating)
                                .put("has_food", p.hasFood)
                                .put("drive_distance_m", p.driveDistanceM)
                        )
                        .put("selected", p.id == selectedId),
                )
            )
        }

        if (matched.isNotEmpty()) {
            // 比較面板最多並排 3 個;已選的若不在前 3 名則換進最後一格
            val top = matched.take(3)
            val selected = matched.firstOrNull { it.id == selectedId }
            val compared = if (selected == null || selected in top) top else top.take(2) + selected
            components.put(
                component(
                    "compare_confirm_panel", "panel_1",
                    JSONObject()
                        .put("candidate_ids", JSONArray(compared.map { it.id }))
                        .put("comparison_text", comparisonText(matched) ?: JSONObject.NULL)
                        .put("confirm_enabled", true),
                )
            )
        }

        val payload = JSONObject()
            .put("components", components)
            .put("clarification_needed", clarification ?: JSONObject.NULL)
        val envelope = JSONObject()
            .put("task_id", "task_demo_%04d".format(taskSeq))
            .put("version", ++version)
            .put("type", "ui_update")
            .put("payload", payload)
        _messages.emit(envelope.toString())
    }

    // 模擬雲端增強:選定候選後才附上取捨說明
    private fun comparisonText(matched: List<Place>): String? {
        val selected = matched.firstOrNull { it.id == selectedId } ?: return null
        val nearest = matched.minBy { it.driveDistanceM }
        val food = if (selected.hasFood) "可順便用餐" else "沒有餐飲"
        return if (nearest.id == selected.id) {
            "(模擬雲端)${selected.name} 是行駛距離最近的選擇,$food,適合短暫休息後盡快上路。"
        } else {
            val extraKm = "%.1f".format((selected.driveDistanceM - nearest.driveDistanceM) / 1000f)
            "(模擬雲端)${selected.name} $food,但比 ${nearest.name} 多開 $extraKm km;趕時間可改選後者。"
        }
    }

    private fun component(type: String, id: String, data: JSONObject) =
        JSONObject().put("type", type).put("id", id).put("data", data)
}
