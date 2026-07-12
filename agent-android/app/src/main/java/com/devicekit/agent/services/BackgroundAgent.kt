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
import com.devicekit.agent.LogBuffer
import com.devicekit.agent.MainActivity
import com.devicekit.agent.R
import com.devicekit.agent.api.DeviceKitClient
import com.devicekit.agent.server.AgentHttpServer
import com.devicekit.agent.server.DiscoveryService
import kotlinx.coroutines.*
import org.json.JSONObject

/**
 * Foreground service that:
 * 1. Maintains a heartbeat with the DeviceKit server
 * 2. Periodically pushes full device state
 * 3. Polls for commands from the server
 * 4. Survives activity destruction (runs in background)
 * 5. Runs on-device metrics collection
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
    private var commandPoller: CommandPoller? = null
    private var otaUpdater: OtaUpdater? = null
    private var metricsCollector: MetricsCollector? = null
    private var httpServer: AgentHttpServer? = null
    private var discoveryService: DiscoveryService? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        Log.i(TAG, "Background Agent created")
        LogBuffer.log("BackgroundAgent", "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val serverUrl = intent?.getStringExtra("server_url")
        if (serverUrl != null) {
            DeviceState.serverUrl = serverUrl
        }

        startForeground(NOTIFICATION_ID, buildNotification("Starting..."))
        startHttpServer()
        startDiscoveryService()
        startMetricsCollection()
        startAgent()

        return START_STICKY
    }

    private fun startAgent() {
        scope.launch {
            // Try to register with the backend server, but don't block local functionality.
            // The embedded HTTP server and metrics run independently.
            var registered = false
            var attempts = 0
            val maxAttempts = 3

            while (!registered && attempts < maxAttempts) {
                attempts++
                registered = registerWithServer()
                if (registered) {
                    DeviceState.isConnected = true
                    updateNotification("Connected to ${DeviceState.serverUrl}")
                    LogBuffer.log("BackgroundAgent", "Connected to ${DeviceState.serverUrl}")
                    startHeartbeat()
                    startStateReporting()
                    startCommandPolling()
                    startOtaUpdater()
                } else {
                    LogBuffer.log("BackgroundAgent", "Server connection attempt $attempts/$maxAttempts failed", LogBuffer.Level.ERROR)
                    if (attempts < maxAttempts) {
                        delay(5_000)
                    }
                }
            }

            if (!registered) {
                // Server unreachable — continue in standalone mode with local HTTP server + metrics
                DeviceState.isConnected = false
                DeviceState.deviceId = "${Build.MANUFACTURER}_${Build.MODEL}".replace(" ", "_")
                updateNotification("Running locally (port ${AgentHttpServer.DEFAULT_PORT})")
                LogBuffer.log("BackgroundAgent", "Server unreachable after $maxAttempts attempts. Running in standalone mode.", LogBuffer.Level.ERROR)
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
            // plan 25 part 2: advertise version from BuildConfig (not a hardcoded string) so
            // the fleet version view + OTA targeting see the real running build.
            put("agent_version", com.devicekit.agent.BuildConfig.VERSION_NAME)
            put("agent_version_code", com.devicekit.agent.BuildConfig.VERSION_CODE)
            // Capabilities as a MAP (FLEET_CONTRACT + FQL `can.*` expect a map, not an array).
            // `batch_survey` opts this agent into one-round-trip probes; the backend falls back
            // to the composed path for any agent that omits it.
            put("capabilities", JSONObject().apply {
                put("accessibility", true)
                put("keyboard_detection", true)
                put("notification_listener", true)
                put("state_reporting", true)
                put("command_receiver", true)
                put("metrics_collection", true)
                put("survey", true)
                put("batch_survey", true)
                put("android_api", Build.VERSION.SDK_INT)
            })
        }

        val deviceId = client.register(deviceInfo)
        if (deviceId != null) {
            DeviceState.deviceId = deviceId
            Log.i(TAG, "Registered with server, device_id=$deviceId")
            LogBuffer.log("BackgroundAgent", "Registered: device_id=$deviceId")
            return true
        }

        // Fallback: try ping only
        if (client.ping()) {
            DeviceState.deviceId = "${Build.MANUFACTURER}_${Build.MODEL}".replace(" ", "_")
            Log.i(TAG, "Server reachable, using fallback device_id=${DeviceState.deviceId}")
            LogBuffer.log("BackgroundAgent", "Fallback registration: ${DeviceState.deviceId}")
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
                    LogBuffer.log("BackgroundAgent", "Heartbeat failed", LogBuffer.Level.ERROR)
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

    /** Poll the backend for read-only survey primitives (plan 25 part 1). */
    private fun startCommandPolling() {
        commandPoller?.stop()
        commandPoller = CommandPoller(this, client, scope).also {
            it.start { DeviceState.deviceId }
        }
        LogBuffer.log("BackgroundAgent", "Command poller started (survey primitives only)")
    }

    /** Periodically check for and apply signed OTA agent updates (plan 25 phase 3). */
    private fun startOtaUpdater() {
        otaUpdater?.stop()
        otaUpdater = OtaUpdater(this, client, scope).also {
            it.start { DeviceState.deviceId }
        }
        LogBuffer.log("BackgroundAgent", "OTA updater started")
    }

    private fun startHttpServer() {
        try {
            httpServer?.stop()
            httpServer = AgentHttpServer(this).also { it.start() }
            LogBuffer.log("BackgroundAgent", "HTTP server started on port ${AgentHttpServer.DEFAULT_PORT}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start HTTP server: ${e.message}")
            LogBuffer.log("BackgroundAgent", "HTTP server failed: ${e.message}", LogBuffer.Level.ERROR)
        }
    }

    private fun startDiscoveryService() {
        try {
            discoveryService?.stop()
            discoveryService = DiscoveryService(this).also { it.start() }
            LogBuffer.log("BackgroundAgent", "Discovery service started on port ${DiscoveryService.DISCOVERY_PORT}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start discovery service: ${e.message}")
            LogBuffer.log("BackgroundAgent", "Discovery service failed: ${e.message}", LogBuffer.Level.ERROR)
        }
    }

    private fun startMetricsCollection() {
        metricsCollector?.stop()
        metricsCollector = MetricsCollector(this).also { it.start() }
        LogBuffer.log("BackgroundAgent", "Metrics collection started")
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
        commandPoller?.stop()
        commandPoller = null
        otaUpdater?.stop()
        otaUpdater = null
        discoveryService?.stop()
        discoveryService = null
        httpServer?.stop()
        httpServer = null
        metricsCollector?.stop()
        metricsCollector = null
        scope.cancel()
        Log.i(TAG, "Background Agent destroyed")
        LogBuffer.log("BackgroundAgent", "Service destroyed")
    }
}
