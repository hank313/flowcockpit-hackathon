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

private val STEP_OPTIONS: Map<String, List<Number>> = mapOf(
    "max_drive_distance_m" to listOf(1000, 3000, 5000, 10000),
    "max_drive_min" to listOf(5, 10, 15, 20),
    "max_drive_km" to listOf(1, 3, 5, 10),
)

private fun formatStep(key: String, value: Number): String {
    val d = value.toDouble()
    val n = if (d % 1.0 == 0.0) d.toInt().toString() else d.toString()
    return when (key) {
        "max_drive_distance_m" -> formatDistance(value.toInt())
        "max_drive_min" -> "$n 分鐘"
        else -> "$n km"
    }
}

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

            val (stepFilters, otherFilters) = data.filters.entries.partition { it.key in STEP_OPTIONS }
            fun label(key: String) = data.labels[key] ?: filterName(key)

            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                otherFilters.forEach { (key, value) ->
                    when (value) {
                        is Boolean, null -> BooleanFilterChip(key, label(key), value as Boolean?, onAction)
                        else -> AttributeChip(describeAttribute(key, value))
                    }
                }
            }

            stepFilters.forEach { (key, value) ->
                StepSelector(key, label(key), value as? Number, onAction)
            }
        }
    }
}

@Composable
private fun BooleanFilterChip(key: String, label: String, value: Boolean?, onAction: (UserAction) -> Unit) {
    FilterChip(
        selected = value == true,
        onClick = { onAction(UserAction.UpdateCondition(key, value != true)) },
        label = {
            Text(
                text = if (value == null) "$label(未知)" else label,
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
private fun StepSelector(key: String, label: String, current: Number?, onAction: (UserAction) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = if (current == null) "$label:未知" else "$label:${formatStep(key, current)}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val options = (STEP_OPTIONS.getValue(key) + listOfNotNull(current))
                .distinctBy { it.toDouble() }
                .sortedBy { it.toDouble() }
            options.forEach { option ->
                FilterChip(
                    selected = option.toDouble() == current?.toDouble(),
                    onClick = { onAction(UserAction.UpdateCondition(key, option)) },
                    label = { Text(formatStep(key, option), style = MaterialTheme.typography.labelLarge) },
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
