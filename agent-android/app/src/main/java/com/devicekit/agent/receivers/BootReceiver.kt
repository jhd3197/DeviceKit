package com.devicekit.agent.receivers

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.devicekit.agent.BuildConfig
import com.devicekit.agent.services.BackgroundAgent
import com.devicekit.agent.services.FaroAgentService
import com.faro.protocol.FaroAgentController

/**
 * Restarts the agent services when the device boots.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return

        // Faro agent (both editions)
        if (FaroAgentController.isEnabled(context)) {
            Log.i("BootReceiver", "Device booted, starting FaroAgentService")
            context.startForegroundService(Intent(context, FaroAgentService::class.java))
        }

        // DeviceKit fleet agent — full edition only (the service isn't even
        // declared in the faro edition's manifest, so starting it would throw)
        if (BuildConfig.FLAVOR == "full") {
            val prefs = context.getSharedPreferences("devicekit", Context.MODE_PRIVATE)
            val serverUrl = prefs.getString("server_url", null)
            val autoStart = prefs.getBoolean("auto_start", false)

            if (autoStart && serverUrl != null) {
                Log.i("BootReceiver", "Device booted, starting BackgroundAgent")
                val serviceIntent = Intent(context, BackgroundAgent::class.java).apply {
                    putExtra("server_url", serverUrl)
                }
                context.startForegroundService(serviceIntent)
            }
        }
    }
}
