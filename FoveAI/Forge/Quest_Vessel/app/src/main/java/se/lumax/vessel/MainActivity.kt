package se.lumax.vessel

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.*

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "LUMAX_Vessel"
        private const val BASE_URL = "https://lumax.1um6a.se/"
        private const val LAUNCH_TIMEOUT_MS = 5000L
        private const val RETRY_DELAY_MS = 2000L
        private const val MAX_RETRIES = 3
    }

    private val mainScope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var launchAttempts = 0
    private var isLaunching = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        Log.d(TAG, "LUMAX Vessel starting - Version OMEGA_238")
        
        // Check network connectivity first
        if (!isNetworkAvailable()) {
            showErrorAndExit("No network connection available")
            return
        }

        // Start the WebXR launch sequence
        launchWebXRExperience()
    }

    private fun launchWebXRExperience() {
        if (isLaunching) {
            Log.w(TAG, "Launch already in progress, ignoring duplicate request")
            return
        }

        isLaunching = true
        launchAttempts++

        Log.d(TAG, "Launch attempt $launchAttempts/$MAX_RETRIES")

        mainScope.launch {
            try {
                // Generate cache buster (less aggressive - use date instead of timestamp)
                val cacheBuster = System.currentTimeMillis() / 1000 // Reduce frequency
                val lumaxUrl = "$BASE_URL?v=$cacheBuster&u=vr&m=xr"
                
                Log.d(TAG, "Launching URL: $lumaxUrl")

                // Try to launch with timeout protection
                val launchSuccess = withTimeoutOrNull(LAUNCH_TIMEOUT_MS) {
                    launchBrowser(lumaxUrl)
                }

                if (launchSuccess == true) {
                    Log.d(TAG, "Browser launch successful")
                    scheduleActivityFinish()
                } else {
                    Log.w(TAG, "Browser launch timed out")
                    handleLaunchFailure("Launch timeout")
                }

            } catch (e: TimeoutCancellationException) {
                Log.e(TAG, "Launch timeout", e)
                handleLaunchFailure("Operation timeout")
            } catch (e: Exception) {
                Log.e(TAG, "Launch failed with exception", e)
                handleLaunchFailure("Launch error: ${e.message}")
            }
        }
    }

    private suspend fun launchBrowser(url: String): Boolean = withContext(Dispatchers.IO) {
        try {
            // Primary: Try Meta Quest Browser
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
                setPackage("com.oculus.browser")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }

            // Check if Oculus Browser is available
            val packageManager = applicationContext.packageManager
            val activities = packageManager.queryIntentActivities(intent, 0)
            
            if (activities.isNotEmpty()) {
                Log.d(TAG, "Launching Meta Quest Browser")
                startActivity(intent)
                return@withContext true
            } else {
                Log.w(TAG, "Meta Quest Browser not found, trying fallback")
                // Fallback: Try system browser
                val fallbackIntent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
                }
                startActivity(fallbackIntent)
                return@withContext true
            }
        } catch (e: Exception) {
            Log.e(TAG, "Browser launch failed", e)
            throw e
        }
    }

    private fun handleLaunchFailure(reason: String) {
        Log.w(TAG, "Launch failed: $reason, attempts: $launchAttempts")

        if (launchAttempts < MAX_RETRIES) {
            // Show retry message
            Handler(Looper.getMainLooper()).post {
                Toast.makeText(
                    this@MainActivity,
                    "Retrying... ($launchAttempts/$MAX_RETRIES)",
                    Toast.LENGTH_SHORT
                ).show()
            }

            // Retry after delay
            Handler(Looper.getMainLooper()).postDelayed({
                isLaunching = false
                launchWebXRExperience()
            }, RETRY_DELAY_MS)
        } else {
            // Max retries reached, show error and exit
            showErrorAndExit("Failed to launch after $MAX_RETRIES attempts: $reason")
        }
    }

    private fun scheduleActivityFinish() {
        // Delay finish to ensure browser has time to start
        Handler(Looper.getMainLooper()).postDelayed({
            try {
                Log.d(TAG, "Finishing launcher activity")
                finish()
            } catch (e: Exception) {
                Log.e(TAG, "Error finishing activity", e)
            }
        }, 1000) // 1 second delay
    }

    private fun showErrorAndExit(message: String) {
        Log.e(TAG, "Error: $message")
        
        Handler(Looper.getMainLooper()).post {
            Toast.makeText(this, "LUMAX Error: $message", Toast.LENGTH_LONG).show()
            
            // Exit after showing error
            Handler(Looper.getMainLooper()).postDelayed({
                finish()
            }, 3000)
        }
    }

    private fun isNetworkAvailable(): Boolean {
        val connectivityManager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivityManager.activeNetwork
        val capabilities = connectivityManager.getNetworkCapabilities(network)
        
        return capabilities?.let {
            it.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            it.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        } ?: false
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "Activity being destroyed")
        
        // Clean up coroutines
        mainScope.cancel()
    }

    override fun onPause() {
        super.onPause()
        Log.d(TAG, "Activity paused")
    }

    override fun onResume() {
        super.onResume()
        Log.d(TAG, "Activity resumed")
    }
}
