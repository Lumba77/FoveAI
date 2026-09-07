package se.lumax.phone

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import okhttp3.WebSocket
import org.json.JSONObject

class SensorHandler(context: Context, private val webSocket: WebSocket?) : SensorEventListener {
    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

    fun start() {
        accelerometer?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        }
        gyroscope?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        }
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event == null || webSocket == null) return

        val type = when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> "accelerometer"
            Sensor.TYPE_GYROSCOPE -> "gyroscope"
            else -> return
        }

        val json = JSONObject().apply {
            put("type", "sensor_data")
            put("sensor", type)
            put("x", event.values[0])
            put("y", event.values[1])
            put("z", event.values[2])
            put("timestamp", event.timestamp)
        }

        webSocket.send(json.toString())
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}