package com.devicekit.agent.services

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.devicekit.agent.DeviceKitApp
import com.devicekit.agent.LogBuffer
import com.devicekit.agent.MainActivity
import com.devicekit.agent.R
import com.faro.protocol.FaroAgentController

/**
 * Foreground service owning the embedded Faro agent daemon — the encrypted,
 * paired link that lets Faro desktop browse/transfer/sync this device's files.
 * Sole owner of the daemon in BOTH editions (full and faro); start/stop it via
 * startForegroundService/stopService, state persists through
 * [FaroAgentController.isEnabled] so BootReceiver can re-arm it.
 */
class FaroAgentService : Service() {

    companion object {
        private const val TAG = "FaroAgentService"
        private const val NOTIFICATION_ID = 1002

        var isRunning: Boolean = false
            private set
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification("Starting..."))
        try {
            val status = FaroAgentController.start(this)
            if (status.error != null) {
                Log.e(TAG, "Faro agent failed to start: ${status.error}")
                LogBuffer.log(TAG, "Start failed: ${status.error}", LogBuffer.Level.ERROR)
                stopSelf()
                return START_NOT_STICKY
            }
            isRunning = true
            val name = FaroAgentController.deviceName(this)
            updateNotification("Visible as \"$name\" · port ${status.port}")
            LogBuffer.log(TAG, "Faro agent listening on port ${status.port} as \"$name\"")
        } catch (e: Throwable) {
            Log.e(TAG, "Faro agent failed to start", e)
            LogBuffer.log(TAG, "Start failed: ${e.message}", LogBuffer.Level.ERROR)
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onDestroy() {
        isRunning = false
        try {
            FaroAgentController.stop(applicationContext)
        } catch (e: Throwable) {
            Log.w(TAG, "Faro agent stop failed", e)
        }
        LogBuffer.log(TAG, "Faro agent stopped")
        super.onDestroy()
    }

    private fun buildNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, DeviceKitApp.CHANNEL_ID)
            .setContentTitle("Faro remote agent")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }
}
