package se.lumax.phone

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "LumaxPhone"
        private const val LOCAL_URL = "ws://192.168.1.100:5176/ws/phone" // Standard local desktop IP
        private const val CLOUD_URL = "wss://lumax.1um6a.se/ws/phone"
    }

    private var useLocalNetwork = true
    private fun getActiveUrl(): String = if (useLocalNetwork) LOCAL_URL else CLOUD_URL

    private lateinit var statusText: TextView
    private lateinit var avatarImage: ImageView
    private lateinit var btnMic: ImageButton
    private lateinit var btnCamera: ImageButton
    private lateinit var btnSensors: ImageButton

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private var webSocket: WebSocket? = null
    
    private var vadHandler: VADHandler? = null
    private var sensorHandler: SensorHandler? = null
    private var isMicOn = false
    private var isCameraOn = false
    private var isSensorsOn = false

    // ... (rest of members)

    private fun startPhoneServices() {
        checkPermissionsAndStartBackgroundService()
        checkAccessibilityService()
        connectWebSocket()
        initVAD()
    }

    private fun checkPermissionsAndStartBackgroundService() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS, Manifest.permission.BODY_SENSORS), 101)
            }
        }
        val serviceIntent = android.content.Intent(this, LumaxBackgroundService::class.java)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }
    }

    private fun checkAccessibilityService() {
        val intent = android.content.Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS)
        intent.flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK
        try {
            // Prompt user to enable the service for permanent background permissions
            Toast.makeText(this, "Please enable Lumax Ghost Accessibility Service", Toast.LENGTH_LONG).show()
            // In a real app we'd check if it's enabled first before firing the intent
            // startActivity(intent) 
        } catch (e: Exception) {}
    }

    private fun initVAD() {
        vadHandler = VADHandler(this) { isSpeaking ->
            runOnUiThread {
                if (isSpeaking) {
                    statusText.text = "LISTENING..."
                    avatarImage.alpha = 1.0f
                } else {
                    statusText.text = if (isMicOn) "CONNECTED TO BASE" else "MIC MUTED"
                    avatarImage.alpha = 0.7f
                }
            }
            if (isSpeaking) {
                webSocket?.send("{\"event\": \"speech_detected\", \"value\": true}")
            }
        }
    }

    private fun connectWebSocket() {
        val url = getActiveUrl()
        statusText.text = if (useLocalNetwork) "CONNECTING (LOCAL)..." else "CONNECTING (CLOUD)..."
        val request = Request.Builder().url(url).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                runOnUiThread {
                    statusText.text = "CONNECTED TO BASE"
                    statusText.setTextColor(ContextCompat.getColor(this@MainActivity, android.R.color.holo_green_light))
                }
                Log.d(TAG, "WebSocket Connected")
                
                // Initialize sensor handler with the active websocket
                sensorHandler = SensorHandler(this@MainActivity, webSocket)
                if (isSensorsOn) sensorHandler?.start()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d(TAG, "Receiving: $text")
                // TODO: Handle avatar commands (blink, speak, etc)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                runOnUiThread {
                    statusText.text = "DISCONNECTED"
                    statusText.setTextColor(ContextCompat.getColor(this@MainActivity, android.R.color.holo_red_light))
                }
                sensorHandler?.stop()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                runOnUiThread {
                    statusText.text = "CONNECTION FAILED"
                    statusText.setTextColor(ContextCompat.getColor(this@MainActivity, android.R.color.holo_red_light))
                }
                Log.e(TAG, "WebSocket Error on \${getActiveUrl()}: \${t.message}")
                sensorHandler?.stop()
                
                // Intelligent Network Routing: If local fails, switch to Cloud. If Cloud fails, switch to local.
                useLocalNetwork = !useLocalNetwork
                
                // Attempt reconnect after delay with the new URL
                lifecycleScope.launch(Dispatchers.IO) {
                    kotlinx.coroutines.delay(3000)
                    runOnUiThread { connectWebSocket() }
                }
            }
        })
    }

    private fun toggleMic() {
        isMicOn = !isMicOn
        if (isMicOn) {
            vadHandler?.start()
            statusText.text = "CONNECTED TO BASE"
        } else {
            vadHandler?.stop()
            statusText.text = "MIC MUTED"
        }
        updateButtonUI()
    }

    private fun toggleCamera() {
        isCameraOn = !isCameraOn
        // TODO: Start/Stop camera stream
        updateButtonUI()
    }

    private fun toggleSensors() {
        isSensorsOn = !isSensorsOn
        if (isSensorsOn) {
            sensorHandler?.start()
        } else {
            sensorHandler?.stop()
        }
        updateButtonUI()
    }

    private fun updateButtonUI() {
        btnMic.alpha = if (isMicOn) 1.0f else 0.4f
        btnCamera.alpha = if (isCameraOn) 1.0f else 0.4f
        btnSensors.alpha = if (isSensorsOn) 1.0f else 0.4f
        
        btnMic.setImageResource(if (isMicOn) android.R.drawable.ic_btn_speak_now else android.R.drawable.presence_audio_busy)
    }

    override fun onDestroy() {
        super.onDestroy()
        vadHandler?.stop()
        sensorHandler?.stop()
        webSocket?.close(1000, "App destroyed")
        client.dispatcher.executorService.shutdown()
    }
}
