package com.example.testapp

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Surface
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import com.example.testapp.data.AssetJsonAiBox
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
                // TODO(A2): 換成 WebSocket 實作的 AiBoxGateway
                val controller = remember {
                    CockpitController(AssetJsonAiBox(applicationContext, scope), scope)
                }
                Surface(Modifier.fillMaxSize()) {
                    CockpitScreen(controller, Modifier.safeDrawingPadding())
                }
            }
        }
    }
}