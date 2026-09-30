package com.example.testapp.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.testapp.model.UiComponent
import com.example.testapp.model.UserAction
import com.example.testapp.ui.theme.TestAPPTheme

/** [candidates] 用來把 candidate_ids 對應回卡片資料(名稱、屬性、是否已選) */
@Composable
fun CompareConfirmPanelView(
    data: UiComponent.CompareConfirmPanel,
    candidates: Map<String, UiComponent.CandidateCard>,
    onAction: (UserAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = colors.surfaceVariant),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("候選比較", style = MaterialTheme.typography.titleSmall)

            if (data.candidateIds.isNotEmpty()) {
                Row(
                    modifier = Modifier.height(IntrinsicSize.Min),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    data.candidateIds.forEach { id ->
                        CompareColumn(
                            candidateId = id,
                            card = candidates[id],
                            onClick = { onAction(UserAction.SelectCandidate(id)) },
                            modifier = Modifier.weight(1f).fillMaxHeight(),
                        )
                    }
                }
            }

            ComparisonText(data.comparisonText)
        }
    }
}

@Composable
private fun CompareColumn(
    candidateId: String,
    card: UiComponent.CandidateCard?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme
    val selected = card?.selected == true
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        color = if (selected) colors.primaryContainer.copy(alpha = 0.35f) else colors.surface,
        border = BorderStroke(if (selected) 2.dp else 1.dp, if (selected) colors.primary else colors.outline),
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                text = card?.name ?: candidateId,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (card == null || card.attributes.isEmpty()) {
                AttributeChip(describeAttribute("屬性", null))
            } else {
                card.attributes.forEach { (key, value) ->
                    AttributeChip(describeAttribute(key, value))
                }
            }
        }
    }
}

@Composable
private fun ComparisonText(text: String?) {
    val colors = MaterialTheme.colorScheme
    if (text == null) {
        Text(
            "離線模式:目前為本地比較結果,連網後可取得 AI 取捨說明",
            style = MaterialTheme.typography.bodySmall,
            color = colors.onSurfaceVariant,
        )
        return
    }
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = colors.tertiaryContainer,
        contentColor = colors.onTertiaryContainer,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text("雲端 AI 取捨分析", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
            Text(text, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Preview(widthDp = 420)
@Composable
private fun CompareConfirmPanelPreview() {
    val a = UiComponent.CandidateCard("card_loc_001", "loc_001", "謝孟勳的狗窝", mapOf("indoor" to true, "drive_distance_m" to 1200), false)
    val b = UiComponent.CandidateCard("card_loc_002", "loc_002", "麥當勞-斗六雲林餐廳", mapOf("indoor" to true, "drive_distance_m" to 1800), true)
    TestAPPTheme {
        CompareConfirmPanelView(
            data = UiComponent.CompareConfirmPanel("panel_1", listOf("loc_001", "loc_002"), "麥當勞-斗六雲林餐廳座位較多,但路程稍遠。", true),
            candidates = mapOf("loc_001" to a, "loc_002" to b),
            onAction = {},
        )
    }
}
