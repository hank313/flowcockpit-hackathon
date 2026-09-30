package com.example.testapp.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private const val UNKNOWN = "未知"

/** 篩選條件/屬性 key 的中文名稱;未列出的 key 直接顯示原字串 */
internal fun filterName(key: String): String = when (key) {
    "indoor" -> "室內"
    "has_seating" -> "有座位"
    "has_food" -> "有餐飲"
    "max_drive_distance_m" -> "行駛距離"
    "drive_distance_m" -> "行駛距離"
    "drive_time_min" -> "車程"
    else -> key
}

internal enum class ChipTone { Positive, Negative, Neutral, Unknown }

internal data class AttributeText(val text: String, val tone: ChipTone)

internal fun describeAttribute(key: String, value: Any?): AttributeText {
    if (value == null) return AttributeText("${filterName(key)} $UNKNOWN", ChipTone.Unknown)
    return when (key) {
        "indoor" -> boolText(value, "室內", "戶外")
        "has_seating" -> boolText(value, "有座位", "無座位")
        "has_food" -> boolText(value, "有餐飲", "無餐飲")
        "drive_distance_m", "max_drive_distance_m" -> (value as? Number)
            ?.let { AttributeText("行駛 ${formatDistance(it.toInt())}", ChipTone.Neutral) }
            ?: AttributeText("行駛距離 $UNKNOWN", ChipTone.Unknown)
        "drive_time_min" -> (value as? Number)
            ?.let { AttributeText("車程 ${it.toInt()} 分", ChipTone.Neutral) }
            ?: AttributeText("車程 $UNKNOWN", ChipTone.Unknown)
        else -> when (value) {
            is Boolean -> boolText(value, filterName(key), "無${filterName(key)}")
            else -> AttributeText("${filterName(key)}:$value", ChipTone.Neutral)
        }
    }
}

private fun boolText(value: Any, yes: String, no: String): AttributeText = when (value) {
    true -> AttributeText(yes, ChipTone.Positive)
    false -> AttributeText(no, ChipTone.Negative)
    else -> AttributeText("$yes? $UNKNOWN", ChipTone.Unknown)
}

/** 1000 m 以上顯示為 km,例如 1.5 km、3 km */
internal fun formatDistance(meters: Int): String = when {
    meters < 1000 -> "$meters m"
    meters % 1000 == 0 -> "${meters / 1000} km"
    else -> "%.1f km".format(meters / 1000f)
}

@Composable
internal fun AttributeChip(attribute: AttributeText, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    val (container, content, border) = when (attribute.tone) {
        ChipTone.Positive -> Triple(colors.secondaryContainer, colors.onSecondaryContainer, null)
        ChipTone.Negative -> Triple(colors.surfaceVariant, colors.onSurfaceVariant, null)
        ChipTone.Neutral -> Triple(colors.primaryContainer, colors.onPrimaryContainer, null)
        ChipTone.Unknown -> Triple(Color.Transparent, colors.tertiary, BorderStroke(1.dp, colors.tertiary))
    }
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(8.dp),
        color = container,
        contentColor = content,
        border = border,
    ) {
        Text(
            text = attribute.text,
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}
