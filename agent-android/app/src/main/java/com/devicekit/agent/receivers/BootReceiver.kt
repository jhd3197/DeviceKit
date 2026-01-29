package com.devicekit.agent.receivers

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.devicekit.agent.services.BackgroundAgent

/**
 * Restarts the BackgroundAgent service when the device boots.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.i("BootReceiver", "Device booted, starting BackgroundAgent")

            val prefs = context.getSharedPreferences("devicekit", Context.MODE_PRIVATE)
            val serverUrl = prefs.getString("server_url", null)
            val autoStart = prefs.getBoolean("auto_start", false)

            if (autoStart && serverUrl != null) {
                val serviceIntent = Intent(context, BackgroundAgent::class.java).apply {
                    putExtra("server_url", serverUrl)
                }
                context.startForegroundService(serviceIntent)
            }
        }
    }
}
