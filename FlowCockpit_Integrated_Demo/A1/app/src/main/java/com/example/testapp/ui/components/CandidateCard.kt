package com.example.testapp.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.testapp.model.UiComponent
import com.example.testapp.model.UserAction
import com.example.testapp.ui.theme.TestAPPTheme

/** 候選卡片;[ordinal] 為畫面上的編號,方便使用者用語音說「第二個」 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CandidateCardView(
    data: UiComponent.CandidateCard,
    ordinal: Int,
    onAction: (UserAction) -> Unit,
    modifier: Modifier = Modifier,
    confirmEnabled: Boolean = true,
) {
    val colors = MaterialTheme.colorScheme
    val borderColor by animateColorAsState(
        if (data.selected) colors.primary else colors.outline,
        label = "candidateBorder",
    )
    Card(
        onClick = { onAction(UserAction.SelectCandidate(data.candidateId)) },
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(if (data.selected) 2.dp else 1.dp, borderColor),
        colors = CardDefaults.cardColors(
            containerColor = if (data.selected) colors.primaryContainer.copy(alpha = 0.35f) else colors.surfaceVariant,
        ),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            OrdinalBadge(ordinal, highlighted = data.selected)
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = data.name ?: "名稱未知",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    if (data.attributes.isEmpty() && data.tags.isEmpty()) {
                        AttributeChip(describeAttribute("屬性", null))
                    }
                    data.attributes.forEach { (key, value) ->
                        AttributeChip(describeAttribute(key, value))
                    }
                    data.tags.forEach { AttributeChip(AttributeText(it, ChipTone.Neutral)) }
                }
            }
            Button(
                onClick = { onAction(UserAction.Confirm(data.candidateId)) },
                enabled = confirmEnabled,
                modifier = Modifier.height(52.dp),
                shape = RoundedCornerShape(12.dp),
            ) {
                Text("確認", style = MaterialTheme.typography.titleMedium)
            }
        }
    }
}

@Composable
private fun OrdinalBadge(ordinal: Int, highlighted: Boolean) {
    val colors = MaterialTheme.colorScheme
    Box(
        modifier = Modifier
            .size(40.dp)
            .background(if (highlighted) colors.primary else colors.surface, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = ordinal.toString(),
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = if (highlighted) colors.onPrimary else colors.onSurface,
        )
    }
}

@Preview(widthDp = 420)
@Composable
private fun CandidateCardPreview() {
    TestAPPTheme {
        CandidateCardView(
            data = UiComponent.CandidateCard(
                id = "card_loc_002",
                candidateId = "loc_002",
                name = "湖畔咖啡館",
                attributes = mapOf("indoor" to true, "has_seating" to true, "drive_distance_m" to 1800, "has_food" to null),
                selected = true,
            ),
            ordinal = 2,
            onAction = {},
        )
    }
}
