package com.devicekit.agent

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class DeviceKitApp : Application() {

    companion object {
        const val CHANNEL_ID = "devicekit_agent"
        lateinit var instance: DeviceKitApp
            private set
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        if (BuildConfig.FLAVOR == "full") {
            // Load any per-device HMAC secret issued at enrollment (plan 07) so signed
            // requests resume across restarts. The faro edition never talks to a
            // DeviceKit backend.
            com.devicekit.agent.api.AgentCredentials.init(this)
        }
        createNotificationChannel()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = getString(R.string.notification_channel_description)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }
}
