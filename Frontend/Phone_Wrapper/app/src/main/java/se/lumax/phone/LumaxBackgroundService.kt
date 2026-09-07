package se.lumax.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.MediaPlayer
import android.os.Build
import android.os.IBinder
import android.util.Base64
import android.util.Log
import androidx.core.app.NotificationCompat
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class LumaxBackgroundService : Service() {

    private val TAG = "LumaxBackground"
    private val CHANNEL_ID = "lumax_ghost_channel"
    private val NOTIFICATION_ID = 1984
    
    private val client = OkHttpClient.Builder()
        .pingInterval(30, TimeUnit.SECONDS)
        .build()
    private var webSocket: WebSocket? = null
    private var mediaPlayer: MediaPlayer? = null
    
    // Default to cloud for background service
    private val WS_URL = "wss://lumax.1um6a.se/ws/phone/background"

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, createPersistentNotification())
        connectWebSocket()
    }

    private fun connectWebSocket() {
        val request = Request.Builder().url(WS_URL).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                Log.i(TAG, "Ghost Background Link Established")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    when (json.optString("action")) {
                        "barge_in" -> {
                            val b64 = json.optString("audio")
                            if (b64.isNotEmpty()) playAudioBargeIn(b64)
                        }
                        "notify" -> {
                            val msg = json.optString("text")
                            if (msg.isNotEmpty()) showHeadsUpNotification(msg)
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to parse message: \")
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                reconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                Log.e(TAG, "WS Failure: \")
                reconnect()
            }
        })
    }
    
    private fun reconnect() {
        thread {
            Thread.sleep(5000)
            connectWebSocket()
        }
    }

    private fun playAudioBargeIn(base64Audio: String) {
        try {
            val audioBytes = Base64.decode(base64Audio, Base64.DEFAULT)
            val tempFile = File(cacheDir, "barge_in.wav")
            FileOutputStream(tempFile).use { it.write(audioBytes) }

            mediaPlayer?.release()
            mediaPlayer = MediaPlayer().apply {
                setDataSource(tempFile.absolutePath)
                prepare()
                start()
                setOnCompletionListener {
                    it.release()
                    tempFile.delete()
                }
            }
            Log.i(TAG, "Audio Barge-In Playing...")
        } catch (e: Exception) {
            Log.e(TAG, "Audio Playback Failed: \")
        }
    }

    private fun showHeadsUpNotification(text: String) {
        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE)

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("LUMAX Ghost")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVibrate(longArrayOf(0, 250, 250, 250))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()

        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(System.currentTimeMillis().toInt(), notification)
    }

    private fun createPersistentNotification(): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE)

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Ghost is Watching")
            .setContentText("Proactive Background Link Active")
            .setSmallIcon(android.R.drawable.presence_online)
            .setContentIntent(pendingIntent)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Lumax Background Service",
                NotificationManager.IMPORTANCE_HIGH // Allow heads-up
            ).apply {
                description = "Handles Proactive Ghost Barge-ins"
                enableVibration(true)
            }
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        webSocket?.close(1000, "Service destroyed")
        mediaPlayer?.release()
    }
}
