package com.devicekit.agent.server.routes

import android.content.Context
import android.view.WindowManager
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.File

class ScreenRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            method == NanoHTTPD.Method.GET && uri == "/screen/shot" -> handleScreenshot()
            method == NanoHTTPD.Method.GET && uri == "/screen/rotation" -> handleRotation()
            method == NanoHTTPD.Method.POST && uri == "/screen/wake" -> handleWake()
            method == NanoHTTPD.Method.POST && uri == "/screen/sleep" -> handleSleep()
            else -> null
        }
    }

    private fun handleScreenshot(): NanoHTTPD.Response {
        val tmpFile = File(context.cacheDir, "screenshot.png")
        val result = execShell("screencap -p ${tmpFile.absolutePath}")
        if (result.exitCode != 0 || !tmpFile.exists()) {
            return errorResponse(message = "Screenshot failed: ${result.output}")
        }
        val bytes = tmpFile.readBytes()
        tmpFile.delete()
        return NanoHTTPD.newFixedLengthResponse(
            NanoHTTPD.Response.Status.OK,
            "image/png",
            ByteArrayInputStream(bytes),
            bytes.size.toLong()
        )
    }

    private fun handleRotation(): NanoHTTPD.Response {
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        @Suppress("DEPRECATION")
        val rotation = wm.defaultDisplay.rotation
        return jsonResponse(json = JSONObject().apply {
            put("rotation", rotation)
            put("natural", rotation == 0)
        })
    }

    private fun handleWake(): NanoHTTPD.Response {
        val result = execShell("input keyevent KEYCODE_WAKEUP")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("action", "wake")
        })
    }

    private fun handleSleep(): NanoHTTPD.Response {
        val result = execShell("input keyevent KEYCODE_SLEEP")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("action", "sleep")
        })
    }
}
