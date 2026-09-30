package com.example.testapp.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

// 座艙固定使用深色,不跟隨系統/動態配色
private val CockpitColorScheme = darkColorScheme(
    primary = CockpitPrimary,
    onPrimary = CockpitOnPrimary,
    primaryContainer = CockpitPrimaryContainer,
    onPrimaryContainer = CockpitOnPrimaryContainer,
    secondary = CockpitSecondary,
    secondaryContainer = CockpitSecondaryContainer,
    onSecondaryContainer = CockpitOnSecondaryContainer,
    tertiary = CockpitTertiary,
    tertiaryContainer = CockpitTertiaryContainer,
    onTertiaryContainer = CockpitOnTertiaryContainer,
    background = CockpitBackground,
    onBackground = CockpitOnSurface,
    surface = CockpitSurface,
    onSurface = CockpitOnSurface,
    surfaceVariant = CockpitSurfaceVariant,
    onSurfaceVariant = CockpitOnSurfaceVariant,
    outline = CockpitOutline,
    error = CockpitError,
)

@Composable
fun TestAPPTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = CockpitColorScheme,
        typography = Typography,
        content = content
    )
}