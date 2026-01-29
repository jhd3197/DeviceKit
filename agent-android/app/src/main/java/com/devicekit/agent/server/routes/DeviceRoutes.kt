package com.devicekit.agent.server.routes

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.StatFs
import android.util.DisplayMetrics
import android.view.WindowManager
import com.devicekit.agent.DeviceState
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject

class DeviceRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.GET) return null

        return when (uri) {
            "/ping" -> handlePing()
            "/info" -> handleInfo()
            "/info/battery" -> handleBattery()
            "/info/display" -> handleDisplay()
            "/info/storage" -> handleStorage()
            "/state" -> handleState()
            "/state/keyboard" -> handleKeyboard()
            "/state/notifications" -> handleNotifications()
            else -> null
        }
    }

    private fun handlePing(): NanoHTTPD.Response {
        return jsonResponse(json = JSONObject().apply {
            put("status", "ok")
            put("agent", "devicekit")
            put("version", "1.0.0")
            put("port", AgentHttpServer.DEFAULT_PORT)
        })
    }

    private fun handleInfo(): NanoHTTPD.Response {
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val dm = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(dm)

        return jsonResponse(json = JSONObject().apply {
            put("model", Build.MODEL)
            put("manufacturer", Build.MANUFACTURER)
            put("brand", Build.BRAND)
            put("device", Build.DEVICE)
            put("product", Build.PRODUCT)
            put("sdk", Build.VERSION.SDK_INT)
            put("android_version", Build.VERSION.RELEASE)
            put("serial", Build.BOARD)
            put("display", JSONObject().apply {
                put("width", dm.widthPixels)
                put("height", dm.heightPixels)
                put("density", dm.density)
                put("dpi", dm.densityDpi)
            })
        })
    }

    private fun handleBattery(): NanoHTTPD.Response {
        val intent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val json = JSONObject()
        if (intent != null) {
            val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
            val temp = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0)
            val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
            val health = intent.getIntExtra(BatteryManager.EXTRA_HEALTH, -1)
            val plugged = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)

            json.put("level", if (scale > 0) (level * 100) / scale else level)
            json.put("temperature", temp / 10.0)
            json.put("is_charging", status == BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == BatteryManager.BATTERY_STATUS_FULL)
            json.put("status", when (status) {
                BatteryManager.BATTERY_STATUS_CHARGING -> "charging"
                BatteryManager.BATTERY_STATUS_DISCHARGING -> "discharging"
                BatteryManager.BATTERY_STATUS_FULL -> "full"
                BatteryManager.BATTERY_STATUS_NOT_CHARGING -> "not_charging"
                else -> "unknown"
            })
            json.put("health", when (health) {
                BatteryManager.BATTERY_HEALTH_GOOD -> "good"
                BatteryManager.BATTERY_HEALTH_OVERHEAT -> "overheat"
                BatteryManager.BATTERY_HEALTH_DEAD -> "dead"
                BatteryManager.BATTERY_HEALTH_OVER_VOLTAGE -> "over_voltage"
                else -> "unknown"
            })
            json.put("plugged", when (plugged) {
                BatteryManager.BATTERY_PLUGGED_AC -> "ac"
                BatteryManager.BATTERY_PLUGGED_USB -> "usb"
                BatteryManager.BATTERY_PLUGGED_WIRELESS -> "wireless"
                else -> "none"
            })
        }
        return jsonResponse(json = json)
    }

    private fun handleDisplay(): NanoHTTPD.Response {
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val dm = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(dm)

        @Suppress("DEPRECATION")
        val rotation = wm.defaultDisplay.rotation

        return jsonResponse(json = JSONObject().apply {
            put("width", dm.widthPixels)
            put("height", dm.heightPixels)
            put("density", dm.density)
            put("dpi", dm.densityDpi)
            put("rotation", rotation)
        })
    }

    private fun handleStorage(): NanoHTTPD.Response {
        val volumes = JSONArray()

        // Internal storage
        val internal = Environment.getDataDirectory()
        val internalStat = StatFs(internal.path)
        volumes.put(JSONObject().apply {
            put("name", "internal")
            put("path", internal.absolutePath)
            put("total_bytes", internalStat.totalBytes)
            put("free_bytes", internalStat.freeBytes)
            put("available_bytes", internalStat.availableBytes)
        })

        // External storage (sdcard)
        val external = Environment.getExternalStorageDirectory()
        if (external.exists()) {
            val externalStat = StatFs(external.path)
            volumes.put(JSONObject().apply {
                put("name", "sdcard")
                put("path", external.absolutePath)
                put("total_bytes", externalStat.totalBytes)
                put("free_bytes", externalStat.freeBytes)
                put("available_bytes", externalStat.availableBytes)
            })
        }

        return jsonResponse(json = JSONObject().apply {
            put("volumes", volumes)
        })
    }

    private fun handleState(): NanoHTTPD.Response {
        return jsonResponse(json = DeviceState.toJson())
    }

    private fun handleKeyboard(): NanoHTTPD.Response {
        return jsonResponse(json = JSONObject().apply {
            put("visible", DeviceState.isKeyboardVisible)
            put("focused_field_id", DeviceState.focusedFieldId)
            put("focused_field_type", DeviceState.focusedFieldType)
            put("focused_field_text", DeviceState.focusedFieldText)
            put("focused_package", DeviceState.focusedPackage)
            put("focused_class", DeviceState.focusedClassName)
        })
    }

    private fun handleNotifications(): NanoHTTPD.Response {
        val notifications = JSONArray()
        DeviceState.recentNotifications.forEach { n ->
            notifications.put(JSONObject().apply {
                put("package", n.packageName)
                put("title", n.title)
                put("text", n.text)
                put("timestamp", n.timestamp)
            })
        }
        return jsonResponse(json = JSONObject().apply {
            put("notifications", notifications)
            put("count", notifications.length())
        })
    }
}
