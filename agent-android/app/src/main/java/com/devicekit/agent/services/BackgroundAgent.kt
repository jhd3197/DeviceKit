package com.devicekit.agent.services

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.devicekit.agent.DeviceKitApp
import com.devicekit.agent.DeviceState
import com.devicekit.agent.MainActivity
import com.devicekit.agent.R
import com.devicekit.agent.api.DeviceKitClient
import kotlinx.coroutines.*
import org.json.JSONObject

/**
 * Foreground service that:
 * 1. Maintains a heartbeat with the DeviceKit server
 * 2. Periodically pushes full device state
 * 3. Polls for commands from the server
 * 4. Survives activity destruction (runs in background)
 */
class BackgroundAgent : Service() {

    companion object {
        private const val TAG = "BackgroundAgent"
        private const val NOTIFICATION_ID = 1001
        private const val HEARTBEAT_INTERVAL_MS = 5_000L
        private const val STATE_REPORT_INTERVAL_MS = 2_000L

        var isRunning: Boolean = false
            private set
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val client = DeviceKitClient()
    private var heartbeatJob: Job? = null
    private var stateReportJob: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        Log.i(TAG, "Background Agent created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val serverUrl = intent?.getStringExtra("server_url")
        if (serverUrl != null) {
            DeviceState.serverUrl = serverUrl
        }

        startForeground(NOTIFICATION_ID, buildNotification("Connecting..."))
        startAgent()

        return START_STICKY
    }

    private fun startAgent() {
        scope.launch {
            var registered = false
            while (!registered) {
                registered = registerWithServer()
                if (registered) {
                    DeviceState.isConnected = true
                    updateNotification("Connected to ${DeviceState.serverUrl}")
                    startHeartbeat()
                    startStateReporting()
                } else {
                    DeviceState.isConnected = false
                    updateNotification("Failed to connect - retrying...")
                    delay(5_000)
                }
            }
        }
    }

    private suspend fun registerWithServer(): Boolean {
        val deviceInfo = JSONObject().apply {
            put("model", Build.MODEL)
            put("manufacturer", Build.MANUFACTURER)
            put("brand", Build.BRAND)
            put("sdk", Build.VERSION.SDK_INT)
            put("android_version", Build.VERSION.RELEASE)
            put("product", Build.PRODUCT)
            put("device", Build.DEVICE)
            put("serial", Build.BOARD)
            put("agent_version", "1.0.0")
            put("capabilities", org.json.JSONArray().apply {
                put("accessibility")
                put("keyboard_detection")
                put("notification_listener")
                put("state_reporting")
                put("command_receiver")
            })
        }

        val deviceId = client.register(deviceInfo)
        if (deviceId != null) {
            DeviceState.deviceId = deviceId
            Log.i(TAG, "Registered with server, device_id=$deviceId")
            return true
        }

        // Fallback: try ping only
        if (client.ping()) {
            DeviceState.deviceId = "${Build.MANUFACTURER}_${Build.MODEL}".replace(" ", "_")
            Log.i(TAG, "Server reachable, using fallback device_id=${DeviceState.deviceId}")
            return true
        }

        Log.w(TAG, "Cannot reach server at ${DeviceState.serverUrl}")
        return false
    }

    private fun startHeartbeat() {
        heartbeatJob?.cancel()
        heartbeatJob = scope.launch {
            while (isActive) {
                val deviceId = DeviceState.deviceId ?: continue
                val success = client.heartbeat(deviceId)
                DeviceState.isConnected = success
                if (!success) {
                    Log.w(TAG, "Heartbeat failed")
                    updateNotification("Connection lost - retrying...")
                }
                delay(HEARTBEAT_INTERVAL_MS)
            }
        }
    }

    private fun startStateReporting() {
        stateReportJob?.cancel()
        stateReportJob = scope.launch {
            while (isActive) {
                val state = DeviceState.toJson()
                val success = client.reportState(state)
                if (!success) {
                    Log.w(TAG, "State report failed")
                }
                delay(STATE_REPORT_INTERVAL_MS)
            }
        }
    }

    private fun buildNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, DeviceKitApp.CHANNEL_ID)
            .setContentTitle("DeviceKit Agent")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val notification = buildNotification(text)
        val manager = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
        manager.notify(NOTIFICATION_ID, notification)
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        DeviceState.isConnected = false
        scope.cancel()
        Log.i(TAG, "Background Agent destroyed")
    }
}
