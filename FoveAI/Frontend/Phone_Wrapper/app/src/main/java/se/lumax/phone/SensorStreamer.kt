package se.lumax.phone

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import okhttp3.WebSocket
import org.json.JSONObject

class SensorStreamer(context: Context, private val webSocket: WebSocket?) : SensorEventListener {

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val stepCounter = sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)

    private var lastUpdate: Long = 0

    fun start() {
        accelerometer?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
        }
        stepCounter?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
        }
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event == null) return
        
        val now = System.currentTimeMillis()
        if (now - lastUpdate < 5000) return // Only send every 5 seconds to save battery
        
        val json = JSONObject()
        json.put("event", "sensor_data")
        
        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
                json.put("sensor", "accelerometer")
                json.put("x", event.values[0])
                json.put("y", event.values[1])
                json.put("z", event.values[2])
            }
            Sensor.TYPE_STEP_COUNTER -> {
                json.put("sensor", "step_counter")
                json.put("steps", event.values[0])
            }
        }
        
        webSocket?.send(json.toString())
        lastUpdate = now
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}
