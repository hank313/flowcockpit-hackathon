package com.example.testapp.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.testapp.model.UiComponent
import com.example.testapp.model.UserAction
import com.example.testapp.ui.theme.TestAPPTheme

private val DRIVE_DISTANCE_OPTIONS = listOf(1000, 3000, 5000, 10000)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ConditionControlView(
    data: UiComponent.ConditionControl,
    onAction: (UserAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("篩選條件", style = MaterialTheme.typography.titleSmall)

            if (data.filters.isEmpty()) {
                Text(
                    "尚無條件,按住麥克風說出需求",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            val (distanceFilters, otherFilters) = data.filters.entries.partition {
                it.key == "max_drive_distance_m"
            }

            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                otherFilters.forEach { (key, value) ->
                    when (value) {
                        is Boolean, null -> BooleanFilterChip(key, value as Boolean?, onAction)
                        else -> AttributeChip(describeAttribute(key, value))
                    }
                }
            }

            distanceFilters.forEach { (key, value) ->
                DistanceSelector(key, (value as? Number)?.toInt(), onAction)
            }
        }
    }
}

@Composable
private fun BooleanFilterChip(key: String, value: Boolean?, onAction: (UserAction) -> Unit) {
    FilterChip(
        selected = value == true,
        onClick = { onAction(UserAction.UpdateCondition(key, value != true)) },
        label = {
            Text(
                text = if (value == null) "${filterName(key)}(未知)" else filterName(key),
                style = MaterialTheme.typography.labelLarge,
            )
        },
        colors = FilterChipDefaults.filterChipColors(
            selectedContainerColor = MaterialTheme.colorScheme.primary,
            selectedLabelColor = MaterialTheme.colorScheme.onPrimary,
        ),
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DistanceSelector(key: String, current: Int?, onAction: (UserAction) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = if (current == null) "行駛距離上限:未知" else "行駛距離上限:${formatDistance(current)}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val options = (DRIVE_DISTANCE_OPTIONS + listOfNotNull(current)).distinct().sorted()
            options.forEach { meters ->
                FilterChip(
                    selected = meters == current,
                    onClick = { onAction(UserAction.UpdateCondition(key, meters)) },
                    label = { Text(formatDistance(meters), style = MaterialTheme.typography.labelLarge) },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = MaterialTheme.colorScheme.primary,
                        selectedLabelColor = MaterialTheme.colorScheme.onPrimary,
                    ),
                )
            }
        }
    }
}

@Preview(widthDp = 420)
@Composable
private fun ConditionControlPreview() {
    TestAPPTheme {
        ConditionControlView(
            data = UiComponent.ConditionControl(
                id = "cond_1",
                filters = mapOf("indoor" to true, "has_seating" to true, "has_food" to null, "max_drive_distance_m" to 3000),
            ),
            onAction = {},
        )
    }
}
