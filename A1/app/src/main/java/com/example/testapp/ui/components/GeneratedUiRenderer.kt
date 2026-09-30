package com.example.testapp.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.testapp.model.UiComponent
import com.example.testapp.model.UiDescription
import com.example.testapp.model.UserAction
import com.example.testapp.ui.theme.TestAPPTheme

/** 整個 AI 建議面板可上下滑動:條件 → 候選比較 → 候選地點 */
@Composable
fun GeneratedUiRenderer(
    description: UiDescription,
    onAction: (UserAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    val conditions = description.components.filterIsInstance<UiComponent.ConditionControl>()
    val cards = description.components.filterIsInstance<UiComponent.CandidateCard>()
    val panels = description.components.filterIsInstance<UiComponent.CompareConfirmPanel>()
    val cardsById = cards.associateBy { it.candidateId }
    // confirm_enabled 定義在比較面板,沒有面板時預設可確認
    val confirmEnabled = panels.firstOrNull()?.confirmEnabled ?: true

    // 不用 item key:後端若送出重複 id,LazyColumn 會 crash
    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        description.clarificationNeeded?.let { item { ClarificationPrompt(it) } }
        items(conditions) { ConditionControlView(it, onAction) }
        items(panels) { CompareConfirmPanelView(it, cardsById, onAction) }

        if (cards.isNotEmpty()) {
            item {
                Text(
                    "候選地點(${cards.size})",
                    style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            itemsIndexed(cards) { index, card ->
                CandidateCardView(card, index + 1, onAction, confirmEnabled = confirmEnabled)
            }
        } else if (description.clarificationNeeded == null) {
            item { EmptyResult() }
        }
    }
}

@Composable
fun ClarificationPrompt(question: String, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = colors.tertiaryContainer,
        contentColor = colors.onTertiaryContainer,
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("需要再確認一下", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
            Text(question, style = MaterialTheme.typography.titleMedium)
            Text("按住麥克風回答,或直接調整下方條件", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun EmptyResult() {
    Text(
        "沒有符合條件的地點,試著放寬條件或重新描述需求",
        style = MaterialTheme.typography.bodyLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(vertical = 24.dp),
    )
}

@Preview(widthDp = 440, heightDp = 800)
@Composable
private fun GeneratedUiRendererPreview() {
    TestAPPTheme {
        Surface {
            GeneratedUiRenderer(
                description = UiDescription(
                    components = listOf(
                        UiComponent.ConditionControl("cond_1", mapOf("indoor" to true, "has_seating" to true, "max_drive_distance_m" to 3000)),
                        UiComponent.CandidateCard("card_loc_001", "loc_001", "謝孟勳的狗窝", mapOf("indoor" to true, "drive_distance_m" to 1200), false),
                        UiComponent.CandidateCard("card_loc_002", "loc_002", "麥當勞-斗六雲林餐廳", mapOf("indoor" to true, "drive_distance_m" to 1800), true),
                        UiComponent.CompareConfirmPanel("panel_1", listOf("loc_001", "loc_002"), null, true),
                    ),
                    clarificationNeeded = null,
                ),
                onAction = {},
            )
        }
    }
}
