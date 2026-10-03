package com.example.testapp.ui.screens

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.testapp.ui.theme.MapBackground
import com.example.testapp.ui.theme.MapMajorRoad
import com.example.testapp.ui.theme.MapStreet
import com.example.testapp.ui.theme.TestAPPTheme
import kotlin.math.roundToInt

/** 模擬導航畫面;[destination] 為確認後寫入的目的地名稱 */
@Composable
fun NavigationMap(destination: String?, modifier: Modifier = Modifier) {
    val routeColor = MaterialTheme.colorScheme.primary
    val destinationColor = MaterialTheme.colorScheme.tertiary
    val oldRouteColor = MaterialTheme.colorScheme.onSurfaceVariant
    val pulse by rememberInfiniteTransition(label = "carPulse").animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1600, easing = LinearEasing), RepeatMode.Restart),
        label = "carPulseValue",
    )

    val points = routeFor(destination)
    val isDetour = points !== MAIN_ROUTE
    val progress = remember { Animatable(0f) }
    LaunchedEffect(destination) {
        progress.snapTo(0f)
        progress.animateTo(1f, tween(1400, easing = FastOutSlowInEasing))
    }

    Box(modifier) {
        Canvas(Modifier.fillMaxSize()) {
            drawRect(MapBackground)
            drawStreets()

            if (isDetour) {
                val oldRoute = MAIN_ROUTE.toPath(size)
                drawPath(
                    oldRoute,
                    oldRouteColor.copy(alpha = 0.5f),
                    style = Stroke(
                        6.dp.toPx(),
                        cap = StrokeCap.Round,
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(18f, 14f)),
                    ),
                )
                drawPin(MAIN_ROUTE.last().scale(size), oldRouteColor.copy(alpha = 0.6f))
            }

            val fullRoute = points.toPath(size)
            val measure = PathMeasure().apply { setPath(fullRoute, false) }
            val route = Path().also { measure.getSegment(0f, measure.length * progress.value, it, true) }
            drawPath(route, routeColor.copy(alpha = 0.25f), style = Stroke(26.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            drawPath(route, routeColor, style = Stroke(12.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))

            if (destination != null) {
                drawPin(points.last().scale(size), destinationColor.copy(alpha = progress.value))
            }

            val car = points.first().scale(size)
            drawCircle(routeColor.copy(alpha = 0.35f * (1f - pulse)), (20 + 30 * pulse).dp.toPx(), car)
            drawCar(car, routeColor)
        }

        TurnBanner(
            points = points,
            subtitle = when {
                destination == null -> "國道三號 南下"
                isDetour -> "已重新規劃 · 前往 $destination"
                else -> "前往 $destination"
            },
            modifier = Modifier.align(Alignment.TopStart).padding(24.dp),
        )
        EtaCard(
            destination = destination,
            modifier = Modifier.align(Alignment.BottomStart).padding(24.dp),
        )
    }
}

// 座標為畫面寬高的比例;第一點為車輛位置
private val CAR = Offset(0.42f, 0.80f)
private val MAIN_ROUTE = listOf(CAR, Offset(0.42f, 0.38f), Offset(0.78f, 0.38f), Offset(0.78f, 0.18f))
private val DETOUR_ROUTES = listOf(
    listOf(CAR, Offset(0.42f, 0.60f), Offset(0.18f, 0.60f), Offset(0.18f, 0.30f)),
    listOf(CAR, Offset(0.42f, 0.52f), Offset(0.64f, 0.52f), Offset(0.64f, 0.70f), Offset(0.86f, 0.70f)),
    listOf(CAR, Offset(0.42f, 0.45f), Offset(0.24f, 0.45f), Offset(0.24f, 0.16f), Offset(0.52f, 0.16f)),
)

// 中途地點依名稱挑一條模擬路線,讓不同地點畫出不同路徑
private fun routeFor(destination: String?): List<Offset> =
    if (destination == null || destination == INITIAL_DESTINATION) MAIN_ROUTE
    else DETOUR_ROUTES[Math.floorMod(destination.hashCode(), DETOUR_ROUTES.size)]

private fun Offset.scale(size: Size) = Offset(x * size.width, y * size.height)

private fun List<Offset>.toPath(size: Size) = Path().apply {
    val first = first().scale(size)
    moveTo(first.x, first.y)
    drop(1).forEach { val p = it.scale(size); lineTo(p.x, p.y) }
}

private fun DrawScope.drawPin(center: Offset, color: Color) {
    drawCircle(color, 16.dp.toPx(), center)
    drawCircle(MapBackground.copy(alpha = color.alpha), 6.dp.toPx(), center)
}

private fun DrawScope.drawStreets() {
    val step = 140.dp.toPx()
    val streetWidth = 8.dp.toPx()
    var x = step / 2
    while (x < size.width) {
        drawLine(MapStreet, Offset(x, 0f), Offset(x, size.height), streetWidth)
        x += step
    }
    var y = step / 3
    while (y < size.height) {
        drawLine(MapStreet, Offset(0f, y), Offset(size.width, y), streetWidth)
        y += step
    }
    drawLine(
        MapMajorRoad,
        Offset(0f, size.height * 0.95f),
        Offset(size.width, size.height * 0.05f),
        18.dp.toPx(),
        cap = StrokeCap.Round,
    )
}

private fun DrawScope.drawCar(center: Offset, color: Color) {
    val r = 18.dp.toPx()
    drawCircle(Color.White, r, center)
    val arrow = Path().apply {
        moveTo(center.x, center.y - r * 0.65f)
        lineTo(center.x + r * 0.5f, center.y + r * 0.5f)
        lineTo(center.x, center.y + r * 0.2f)
        lineTo(center.x - r * 0.5f, center.y + r * 0.5f)
        close()
    }
    drawPath(arrow, color)
}

@Composable
private fun TurnBanner(points: List<Offset>, subtitle: String, modifier: Modifier = Modifier) {
    val turnLeft = points.size > 2 && points[2].x < points[1].x
    // 依第一段直行長度換算成模擬公尺數,取到 50 m
    val meters = (((points[0].y - points[1].y) * 1500 / 50).roundToInt() * 50).coerceAtLeast(50)
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                if (turnLeft) "↰" else "↱",
                style = MaterialTheme.typography.displaySmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Column {
                Text(
                    "$meters 公尺後 ${if (turnLeft) "左轉" else "右轉"}",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun EtaCard(destination: String?, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
    ) {
        // 原行程與中途休息點使用不同的模擬數值
        val mainRoute = destination == null || destination == INITIAL_DESTINATION
        Row(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            EtaItem(if (mainRoute) "14:32" else "13:58", "預計抵達")
            EtaItem(if (mainRoute) "38 km" else "4.2 km", "剩餘距離")
            EtaItem(if (mainRoute) "42 分" else "8 分", "剩餘時間")
        }
    }
}

@Composable
private fun EtaItem(value: String, label: String) {
    Column {
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Preview(widthDp = 960, heightDp = 540)
@Composable
private fun NavigationMapPreview() {
    TestAPPTheme {
        NavigationMap(destination = "湖畔咖啡館", modifier = Modifier.fillMaxSize())
    }
}
