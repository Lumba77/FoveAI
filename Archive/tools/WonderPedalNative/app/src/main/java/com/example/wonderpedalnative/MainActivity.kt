package com.example.wonderpedalnative

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.ViewGroup
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.example.wonderpedalnative.theme.WonderPedalNativeTheme
import okhttp3.*
import java.util.concurrent.Executors
import kotlin.math.abs

class MainActivity : ComponentActivity() {

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            // Permission granted
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        setContent {
            WonderPedalNativeTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    WonderPedalApp()
                }
            }
        }
    }
}

@Composable
fun WonderPedalApp() {
    var ipAddress by remember { mutableStateOf("192.168.8.100") }
    var isConnected by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf("Disconnected") }
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    // WebSocket logic
    val webSocketClient = remember {
        var ws: WebSocket? = null
        val client = OkHttpClient()
        object {
            fun connect(ip: String) {
                statusText = "Connecting..."
                val request = Request.Builder().url("ws://$ip:8103/ws").build()
                ws = client.newWebSocket(request, object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        isConnected = true
                        statusText = "Connected!"
                    }
                    override fun onMessage(webSocket: WebSocket, text: String) {
                        Log.d("WonderPedal", "Msg: $text")
                    }
                    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                        isConnected = false
                        statusText = "Disconnected"
                    }
                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                        isConnected = false
                        statusText = "Error: ${t.message}"
                    }
                })
            }
            fun sendKick() {
                if (isConnected) {
                    ws?.send("{\"trigger\": \"kick\"}")
                    Log.d("WonderPedal", "Kick Sent!")
                }
            }
            fun disconnect() {
                ws?.close(1000, null)
                isConnected = false
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Wonder Pedal (Quest 3)", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(16.dp))
        
        OutlinedTextField(
            value = ipAddress,
            onValueChange = { ipAddress = it },
            label = { Text("PC IP Address") },
            modifier = Modifier.fillMaxWidth()
        )
        
        Spacer(modifier = Modifier.height(8.dp))
        
        Row {
            Button(onClick = { 
                if (!isConnected) webSocketClient.connect(ipAddress) 
                else webSocketClient.disconnect()
            }) {
                Text(if (isConnected) "Disconnect" else "Connect")
            }
            Spacer(modifier = Modifier.width(16.dp))
            Text(statusText, modifier = Modifier.padding(top = 12.dp))
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Camera Preview
        Box(modifier = Modifier.fillMaxSize()) {
            AndroidView(
                factory = { ctx ->
                    val previewView = PreviewView(ctx).apply {
                        layoutParams = ViewGroup.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.MATCH_PARENT
                        )
                    }

                    val cameraProviderFuture = ProcessCameraProvider.getInstance(ctx)
                    cameraProviderFuture.addListener({
                        val cameraProvider = cameraProviderFuture.get()

                        val preview = Preview.Builder().build().also {
                            it.setSurfaceProvider(previewView.surfaceProvider)
                        }

                        val imageAnalysis = ImageAnalysis.Builder()
                            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                            .build()
                            .also {
                                it.setAnalyzer(Executors.newSingleThreadExecutor(), MotionAnalyzer {
                                    // Run on UI thread to update any states if needed
                                    webSocketClient.sendKick()
                                })
                            }

                        // Use front camera for Quest 3 (passthrough cameras)
                        val cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA

                        try {
                            cameraProvider.unbindAll()
                            cameraProvider.bindToLifecycle(
                                lifecycleOwner,
                                cameraSelector,
                                preview,
                                imageAnalysis
                            )
                        } catch (exc: Exception) {
                            Log.e("WonderPedal", "Use case binding failed", exc)
                        }
                    }, ContextCompat.getMainExecutor(ctx))
                    
                    previewView
                },
                modifier = Modifier.fillMaxSize()
            )
        }
    }
}

class MotionAnalyzer(private val onMotionDetected: () -> Unit) : ImageAnalysis.Analyzer {
    private var lastPixels: ByteArray? = null
    private var cooldown = 0L

    override fun analyze(image: ImageProxy) {
        val currentTime = System.currentTimeMillis()
        if (currentTime - cooldown < 200) { // 200ms cooldown for kicks
            image.close()
            return
        }

        val buffer = image.planes[0].buffer
        val data = ByteArray(buffer.remaining())
        buffer.get(data)

        if (lastPixels != null && lastPixels!!.size == data.size) {
            var diffSum = 0L
            // Sample pixels to save CPU
            for (i in 0 until data.size step 20) {
                val p1 = data[i].toInt() and 0xFF
                val p2 = lastPixels!![i].toInt() and 0xFF
                diffSum += abs(p1 - p2)
            }
            val avgDiff = diffSum / (data.size / 20)
            
            // Magic threshold for motion detection (needs tuning)
            if (avgDiff > 12) { 
                onMotionDetected()
                cooldown = currentTime
            }
        }
        lastPixels = data
        image.close()
    }
}
