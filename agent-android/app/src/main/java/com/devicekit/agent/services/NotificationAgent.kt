package com.devicekit.agent.services

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.devicekit.agent.DeviceState
import com.devicekit.agent.api.DeviceKitClient
import kotlinx.coroutines.*
import org.json.JSONObject

/**
 * Listens for notifications posted on the device and forwards them
 * to the DeviceKit server. Requires user to grant notification access
 * in Settings > Apps > Special access > Notification access.
 */
class NotificationAgent : NotificationListenerService() {

    companion object {
        private const val TAG = "NotificationAgent"
        var isRunning: Boolean = false
            private set
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val client = DeviceKitClient()

    override fun onListenerConnected() {
        super.onListenerConnected()
        isRunning = true
        Log.i(TAG, "Notification Agent connected")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        sbn ?: return

        val extras = sbn.notification?.extras ?: return
        val title = extras.getString("android.title")
        val text = extras.getCharSequence("android.text")?.toString()
        val pkg = sbn.packageName

        // Skip our own notifications
        if (pkg == "com.devicekit.agent") return

        Log.d(TAG, "Notification: [$pkg] $title: $text")

        val info = DeviceState.NotificationInfo(
            packageName = pkg,
            title = title,
            text = text,
            timestamp = sbn.postTime
        )
        DeviceState.addNotification(info)

        // Forward to server
        val deviceId = DeviceState.deviceId ?: return
        scope.launch {
            try {
                val data = JSONObject().apply {
                    put("package", pkg)
                    put("title", title)
                    put("text", text)
                    put("post_time", sbn.postTime)
                    put("key", sbn.key)
                }
                client.reportEvent(deviceId, "notification_posted", data)
            } catch (e: Exception) {
                Log.w(TAG, "Failed to report notification: ${e.message}")
            }
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        // Optional: track dismissed notifications
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        isRunning = false
        Log.i(TAG, "Notification Agent disconnected")
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        scope.cancel()
    }
}
