package com.example.testapp

import android.Manifest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.example.testapp.data.HttpAiBox
import com.example.testapp.ui.screens.CockpitController
import com.example.testapp.ui.screens.CockpitScreen
import com.example.testapp.ui.theme.TestAPPTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TestAPPTheme {
                val scope = rememberCoroutineScope()
                val preferences = remember {
                    getSharedPreferences(AI_BOX_PREFERENCES, MODE_PRIVATE)
                }
                var aiBoxHost by remember {
                    mutableStateOf(
                        preferences.getString(AI_BOX_HOST_KEY, BuildConfig.AI_BOX_HOST)
                            ?: BuildConfig.AI_BOX_HOST,
                    )
                }
                var showConnectionSettings by remember { mutableStateOf(false) }
                val micPermission = rememberLauncherForActivityResult(
                    ActivityResultContracts.RequestPermission(),
                ) {}
                LaunchedEffect(Unit) { micPermission.launch(Manifest.permission.RECORD_AUDIO) }

                val gateway = remember(aiBoxHost) {
                    HttpAiBox(applicationContext, scope, aiBoxHost)
                }
                DisposableEffect(gateway) {
                    onDispose { gateway.close() }
                }
                val controller = remember(gateway) {
                    CockpitController(gateway, scope)
                }
                Surface(Modifier.fillMaxSize()) {
                    CockpitScreen(
                        controller = controller,
                        onOpenConnectionSettings = { showConnectionSettings = true },
                        modifier = Modifier.safeDrawingPadding(),
                    )
                }

                if (showConnectionSettings) {
                    AiBoxConnectionDialog(
                        currentHost = aiBoxHost,
                        defaultHost = BuildConfig.AI_BOX_HOST,
                        onDismiss = { showConnectionSettings = false },
                        onSave = { newHost ->
                            preferences.edit().putString(AI_BOX_HOST_KEY, newHost).apply()
                            aiBoxHost = newHost
                            showConnectionSettings = false
                        },
                    )
                }
            }
        }
    }

    private companion object {
        const val AI_BOX_PREFERENCES = "ai_box_connection"
        const val AI_BOX_HOST_KEY = "host"
    }
}

@Composable
private fun AiBoxConnectionDialog(
    currentHost: String,
    defaultHost: String,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit,
) {
    var input by remember(currentHost) { mutableStateOf(currentHost) }
    val normalized = input.trim()
        .removePrefix("http://")
        .removePrefix("https://")
        .removePrefix("ws://")
        .removePrefix("wss://")
        .trimEnd('/')
    val match = remember(normalized) {
        Regex("^[A-Za-z0-9.-]+:([0-9]{1,5})$").matchEntire(normalized)
    }
    val port = match?.groupValues?.getOrNull(1)?.toIntOrNull()
    val valid = match != null && port != null && port in 1..65535

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("AI Box 連線設定") },
        text = {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                singleLine = true,
                label = { Text("IP 位址與連接埠") },
                placeholder = { Text("例如 10.53.140.238:8000") },
                supportingText = {
                    Text(
                        if (valid) "儲存後會立即重新連線"
                        else "格式應為 IP:連接埠，例如 192.168.0.190:8000",
                    )
                },
                isError = input.isNotBlank() && !valid,
            )
        },
        confirmButton = {
            TextButton(onClick = { onSave(normalized) }, enabled = valid) {
                Text("儲存並重連")
            }
        },
        dismissButton = {
            TextButton(onClick = {
                if (normalized == defaultHost) onDismiss() else input = defaultHost
            }) {
                Text(if (normalized == defaultHost) "取消" else "使用預設值")
            }
        },
    )
}
