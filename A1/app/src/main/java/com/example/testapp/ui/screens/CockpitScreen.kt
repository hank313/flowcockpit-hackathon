package com.example.testapp.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.example.testapp.R
import com.example.testapp.model.UiDescription
import com.example.testapp.model.UserAction
import com.example.testapp.ui.components.GeneratedUiRenderer

@Composable
fun CockpitScreen(controller: CockpitController, modifier: Modifier = Modifier) {
    CockpitLayout(
        ui = controller.ui,
        micState = controller.micState,
        destination = controller.destination,
        onMicPressed = controller::onMicPressed,
        onMicReleased = controller::onMicReleased,
        onAction = controller::onAction,
        onDismissPanel = controller::dismissPanel,
        modifier = modifier,
    )
}

@Composable
private fun CockpitLayout(
    ui: UiDescription?,
    micState: MicState,
    destination: String?,
    onMicPressed: () -> Unit,
    onMicReleased: () -> Unit,
    onAction: (UserAction) -> Unit,
    onDismissPanel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // 退場動畫期間 ui 已為 null,沿用最後一份內容避免面板閃空
    var lastUi by remember { mutableStateOf(ui) }
    LaunchedEffect(ui) { if (ui != null) lastUi = ui }
    val shownUi = ui ?: lastUi

    Row(modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        NavigationMap(
            destination = destination,
            modifier = Modifier.weight(1f).fillMaxHeight(),
        )

        AnimatedVisibility(
            visible = ui != null,
            enter = slideInHorizontally { it } + fadeIn(),
            exit = slideOutHorizontally { it } + fadeOut(),
        ) {
            shownUi?.let { AiPanel(it, onAction, onDismissPanel) }
        }

        MicRail(
            micState = micState,
            onPressed = onMicPressed,
            onReleased = onMicReleased,
            modifier = Modifier.width(128.dp).fillMaxHeight(),
        )
    }
}

@Composable
private fun AiPanel(
    ui: UiDescription,
    onAction: (UserAction) -> Unit,
    onDismiss: () -> Unit,
) {
    Surface(
        modifier = Modifier.width(460.dp).fillMaxHeight(),
        color = MaterialTheme.colorScheme.surface,
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 12.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "AI 建議",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = onDismiss) { Text("收合") }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outline)
            GeneratedUiRenderer(ui, onAction, Modifier.weight(1f))
        }
    }
}

@Composable
private fun MicRail(
    micState: MicState,
    onPressed: () -> Unit,
    onReleased: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(modifier = modifier, color = MaterialTheme.colorScheme.surfaceVariant) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            MicButton(micState, onPressed, onReleased)
            Text(
                text = when (micState) {
                    MicState.Idle -> "按住說話"
                    MicState.Listening -> "聆聽中\n放開送出"
                    MicState.Processing -> "AI 處理中"
                },
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 16.dp),
            )
        }
    }
}

@Composable
private fun MicButton(
    micState: MicState,
    onPressed: () -> Unit,
    onReleased: () -> Unit,
) {
    val currentOnPressed by rememberUpdatedState(onPressed)
    val currentOnReleased by rememberUpdatedState(onReleased)
    val colors = MaterialTheme.colorScheme
    val listening = micState == MicState.Listening
    val pulse by rememberInfiniteTransition(label = "micPulse").animateFloat(
        initialValue = 1f,
        targetValue = 1.12f,
        animationSpec = infiniteRepeatable(tween(500), RepeatMode.Reverse),
        label = "micPulseValue",
    )

    Box(
        modifier = Modifier
            .size(96.dp)
            .scale(if (listening) pulse else 1f)
            .background(if (listening) colors.error else colors.primary, CircleShape)
            .pointerInput(Unit) {
                detectTapGestures(
                    onPress = {
                        currentOnPressed()
                        tryAwaitRelease()
                        currentOnReleased()
                    },
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        if (micState == MicState.Processing) {
            CircularProgressIndicator(color = colors.onPrimary, modifier = Modifier.size(40.dp))
        } else {
            Icon(
                painter = painterResource(R.drawable.ic_mic),
                contentDescription = "按住說話",
                tint = if (listening) colors.onError else colors.onPrimary,
                modifier = Modifier.size(44.dp),
            )
        }
    }
}
