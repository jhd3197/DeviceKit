package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject

/**
 * Device settings control: WiFi, brightness, airplane mode, volume, etc.
 * Uses shell commands (settings/svc) for maximum compatibility.
 */
class SettingsRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            // GET
            method == NanoHTTPD.Method.GET && uri == "/settings/wifi" -> handleGetWifi()
            method == NanoHTTPD.Method.GET && uri == "/settings/brightness" -> handleGetBrightness()
            method == NanoHTTPD.Method.GET && uri == "/settings/airplane" -> handleGetAirplane()
            method == NanoHTTPD.Method.GET && uri == "/settings/volume" -> handleGetVolume()
            method == NanoHTTPD.Method.GET && uri == "/settings/bluetooth" -> handleGetBluetooth()
            method == NanoHTTPD.Method.GET && uri == "/settings/location" -> handleGetLocation()
            method == NanoHTTPD.Method.GET && uri == "/settings/auto_rotate" -> handleGetAutoRotate()

            // POST
            method == NanoHTTPD.Method.POST && uri == "/settings/wifi" -> handleSetWifi(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/settings/brightness" -> handleSetBrightness(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/settings/airplane" -> handleSetAirplane(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/settings/volume" -> handleSetVolume(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/settings/bluetooth" -> handleSetBluetooth(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/settings/location" -> handleSetLocation(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/settings/auto_rotate" -> handleSetAutoRotate(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/settings/locale" -> handleSetLocale(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/settings/screen_timeout" -> handleSetScreenTimeout(session, bodyParams)
            else -> null
        }
    }

    // WiFi
    private fun handleGetWifi(): NanoHTTPD.Response {
        val result = execShell("settings get global wifi_on")
        return jsonResponse(json = JSONObject().apply {
            put("enabled", result.output.trim() == "1")
        })
    }

    private fun handleSetWifi(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val enabled = body.optBoolean("enabled", true)
        val cmd = if (enabled) "svc wifi enable" else "svc wifi disable"
        val result = execShell(cmd)
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("enabled", enabled)
        })
    }

    // Brightness
    private fun handleGetBrightness(): NanoHTTPD.Response {
        val brightness = execShell("settings get system screen_brightness").output.trim()
        val mode = execShell("settings get system screen_brightness_mode").output.trim()
        return jsonResponse(json = JSONObject().apply {
            put("brightness", brightness.toIntOrNull() ?: 0)
            put("auto", mode == "1")
            put("max", 255)
        })
    }

    private fun handleSetBrightness(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val results = mutableListOf<ShellResult>()

        if (body.has("auto")) {
            val auto = body.getBoolean("auto")
            results.add(execShell("settings put system screen_brightness_mode ${if (auto) 1 else 0}"))
        }
        if (body.has("level")) {
            val level = body.getInt("level").coerceIn(0, 255)
            results.add(execShell("settings put system screen_brightness $level"))
        }

        return jsonResponse(json = JSONObject().apply {
            put("success", results.all { it.exitCode == 0 })
        })
    }

    // Airplane mode
    private fun handleGetAirplane(): NanoHTTPD.Response {
        val result = execShell("settings get global airplane_mode_on")
        return jsonResponse(json = JSONObject().apply {
            put("enabled", result.output.trim() == "1")
        })
    }

    private fun handleSetAirplane(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val enabled = body.optBoolean("enabled", true)
        val value = if (enabled) "1" else "0"
        execShell("settings put global airplane_mode_on $value")
        val result = execShell("am broadcast -a android.intent.action.AIRPLANE_MODE --ez state $enabled")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("enabled", enabled)
        })
    }

    // Volume
    private fun handleGetVolume(): NanoHTTPD.Response {
        val media = execShell("settings get system volume_music_speaker").output.trim()
        val ring = execShell("settings get system volume_ring_speaker").output.trim()
        val alarm = execShell("settings get system volume_alarm_speaker").output.trim()
        return jsonResponse(json = JSONObject().apply {
            put("media", media.toIntOrNull() ?: -1)
            put("ring", ring.toIntOrNull() ?: -1)
            put("alarm", alarm.toIntOrNull() ?: -1)
        })
    }

    private fun handleSetVolume(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val stream = body.optString("stream", "media")
        val level = body.optInt("level", 7)

        // Use media session command for more reliable volume control
        val streamIndex = when (stream) {
            "media" -> 3
            "ring" -> 2
            "alarm" -> 4
            "notification" -> 5
            "system" -> 1
            else -> 3
        }
        val result = execShell("media volume --stream $streamIndex --set $level --show")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("stream", stream)
            put("level", level)
        })
    }

    // Bluetooth
    private fun handleGetBluetooth(): NanoHTTPD.Response {
        val result = execShell("settings get global bluetooth_on")
        return jsonResponse(json = JSONObject().apply {
            put("enabled", result.output.trim() == "1")
        })
    }

    private fun handleSetBluetooth(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val enabled = body.optBoolean("enabled", true)
        val cmd = if (enabled) "svc bluetooth enable" else "svc bluetooth disable"
        val result = execShell(cmd)
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("enabled", enabled)
        })
    }

    // Location
    private fun handleGetLocation(): NanoHTTPD.Response {
        val result = execShell("settings get secure location_mode")
        return jsonResponse(json = JSONObject().apply {
            put("mode", result.output.trim().toIntOrNull() ?: 0)
            put("enabled", (result.output.trim().toIntOrNull() ?: 0) > 0)
        })
    }

    private fun handleSetLocation(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val enabled = body.optBoolean("enabled", true)
        val mode = if (enabled) 3 else 0 // 3 = high accuracy, 0 = off
        val result = execShell("settings put secure location_mode $mode")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("enabled", enabled)
        })
    }

    // Auto-rotate
    private fun handleGetAutoRotate(): NanoHTTPD.Response {
        val result = execShell("settings get system accelerometer_rotation")
        return jsonResponse(json = JSONObject().apply {
            put("enabled", result.output.trim() == "1")
        })
    }

    private fun handleSetAutoRotate(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val enabled = body.optBoolean("enabled", true)
        val result = execShell("settings put system accelerometer_rotation ${if (enabled) 1 else 0}")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("enabled", enabled)
        })
    }

    // Locale
    private fun handleSetLocale(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val locale = body.optString("locale", "")
        if (locale.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "locale required (e.g. 'en-US')")
        }
        val result = execShell("settings put system system_locales $locale")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("locale", locale)
        })
    }

    // Screen timeout
    private fun handleSetScreenTimeout(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val ms = body.optInt("timeout_ms", 60000)
        val result = execShell("settings put system screen_off_timeout $ms")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("timeout_ms", ms)
        })
    }
}
