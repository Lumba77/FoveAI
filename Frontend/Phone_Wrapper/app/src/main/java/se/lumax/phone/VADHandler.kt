package se.lumax.phone

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.nio.FloatBuffer
import java.util.Collections

class VADHandler(
    private val context: Context,
    private val onSpeechDetected: (Boolean) -> Unit
) {
    private val TAG = "VADHandler"
    private val SAMPLE_RATE = 16000
    private val FRAME_SIZE = 512 // Silero VAD works with 256, 512, 768 or 1024 frames for 16kHz
    
    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var recordingJob: Job? = null
    
    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private var session: OrtSession? = null

    init {
        try {
            val modelBytes = context.assets.open("silero_vad.onnx").use { it.readBytes() }
            session = env.createSession(modelBytes)
            Log.d(TAG, "Silero VAD model loaded successfully")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load Silero VAD model: ${e.message}")
        }
    }

    @SuppressLint("MissingPermission")
    fun start() {
        if (isRecording) return
        
        val bufferSize = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        ).coerceAtLeast(FRAME_SIZE * 2)

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferSize
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord initialization failed")
            return
        }

        audioRecord?.startRecording()
        isRecording = true
        
        recordingJob = CoroutineScope(Dispatchers.Default).launch {
            val audioBuffer = ShortArray(FRAME_SIZE)
            val floatBuffer = FloatArray(FRAME_SIZE)
            
            // Model state tensors (Silero VAD v4/v5/v6 needs these)
            // v6 usually uses h(2, 1, 64) and c(2, 1, 64)
            var h = FloatArray(2 * 1 * 64) { 0.0f }
            var c = FloatArray(2 * 1 * 64) { 0.0f }

            while (isRecording) {
                val read = audioRecord?.read(audioBuffer, 0, FRAME_SIZE) ?: 0
                if (read == FRAME_SIZE) {
                    // Convert to float [-1.0, 1.0]
                    for (i in 0 until read) {
                        floatBuffer[i] = audioBuffer[i] / 32768.0f
                    }
                    
                    if (session != null) {
                        val result = processFrame(floatBuffer, h, c)
                        if (result != null) {
                            h = result.h
                            c = result.c
                            onSpeechDetected(result.probability > 0.4f) // Slightly lower threshold
                        }
                    }
                }
            }
        }
    }

    private data class VADResult(val probability: Float, val h: FloatArray, val c: FloatArray)

    private fun processFrame(frame: FloatArray, h: FloatArray, c: FloatArray): VADResult? {
        val session = session ?: return null
        
        val inputName = session.inputNames.first() // usually "input"
        val srName = "sr"
        val hName = "h"
        val cName = "c"
        
        val frameBuffer = FloatBuffer.wrap(frame)
        val hBuffer = FloatBuffer.wrap(h)
        val cBuffer = FloatBuffer.wrap(c)
        
        val inputTensor = OnnxTensor.createTensor(env, frameBuffer, longArrayOf(1, FRAME_SIZE.toLong()))
        val srTensor = OnnxTensor.createTensor(env, longArrayOf(SAMPLE_RATE.toLong()))
        val hTensor = OnnxTensor.createTensor(env, hBuffer, longArrayOf(2, 1, 64))
        val cTensor = OnnxTensor.createTensor(env, cBuffer, longArrayOf(2, 1, 64))

        val inputs = mutableMapOf<String, OnnxTensor>()
        inputs["input"] = inputTensor
        inputs["sr"] = srTensor
        inputs["h"] = hTensor
        inputs["c"] = cTensor

        return try {
            val outputs = session.run(inputs)
            val probability = (outputs[0].value as Array<FloatArray>)[0][0]
            val newH = (outputs[1].value as Array<Array<FloatArray>>).flatten().flatMap { it.toList() }.toFloatArray()
            val newC = (outputs[2].value as Array<Array<FloatArray>>).flatten().flatMap { it.toList() }.toFloatArray()
            
            VADResult(probability, newH, newC)
        } catch (e: Exception) {
            null
        } finally {
            inputTensor.close()
            srTensor.close()
            hTensor.close()
            cTensor.close()
        }
    }

    private fun Array<Array<FloatArray>>.flatten(): List<FloatArray> {
        val result = mutableListOf<FloatArray>()
        for (a in this) {
            for (b in a) {
                result.add(b)
            }
        }
        return result
    }

    fun stop() {
        isRecording = false
        recordingJob?.cancel()
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
    }
}