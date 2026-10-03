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
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import com.example.testapp.data.HttpAiBox
import com.example.testapp.ui.screens.CockpitController
import com.example.testapp.ui.screens.CockpitScreen
import com.example.testapp.ui.theme.TestAPPTheme

/** D 後端位址。Android 模擬器連電腦用 10.0.2.2;實體平板改成 AI Box 的區網 IP */
private const val AI_BOX_HOST = "10.0.2.2:8000"

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TestAPPTheme {
                val scope = rememberCoroutineScope()
                val micPermission = rememberLauncherForActivityResult(
                    ActivityResultContracts.RequestPermission(),
                ) {}
                LaunchedEffect(Unit) { micPermission.launch(Manifest.permission.RECORD_AUDIO) }

                val controller = remember {
                    CockpitController(HttpAiBox(applicationContext, scope, AI_BOX_HOST), scope)
                }
                Surface(Modifier.fillMaxSize()) {
                    CockpitScreen(controller, Modifier.safeDrawingPadding())
                }
            }
        }
    }
}
