package com.devicekit.agent.receivers

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.devicekit.agent.DeviceState

/**
 * Receives commands via ADB broadcast. This allows DeviceKit to send
 * commands to the agent without HTTP, using:
 *
 *   adb shell am broadcast -a com.devicekit.agent.COMMAND \
 *       --es type "set_server" \
 *       --es value "http://192.168.1.100:5050"
 *
 * Supported commands:
 *   - set_server: Change the server URL
 *   - get_state: Log current device state (for debugging)
 *   - set_device_id: Override the device ID
 */
class CommandReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "CommandReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != "com.devicekit.agent.COMMAND") return

        val type = intent.getStringExtra("type") ?: return
        val value = intent.getStringExtra("value")

        Log.i(TAG, "Received command: type=$type, value=$value")

        when (type) {
            "set_server" -> {
                if (value != null) {
                    DeviceState.serverUrl = value
                    val prefs = context.getSharedPreferences("devicekit", Context.MODE_PRIVATE)
                    prefs.edit().putString("server_url", value).apply()
                    Log.i(TAG, "Server URL set to $value")
                }
            }
            "get_state" -> {
                Log.i(TAG, "Current state:\n${DeviceState.toDisplayString()}")
            }
            "set_device_id" -> {
                if (value != null) {
                    DeviceState.deviceId = value
                    Log.i(TAG, "Device ID set to $value")
                }
            }
        }
    }
}
