package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject

class InputRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.POST) return null

        return when (uri) {
            "/input/tap" -> handleTap(session, bodyParams)
            "/input/swipe" -> handleSwipe(session, bodyParams)
            "/input/text" -> handleText(session, bodyParams)
            "/input/key" -> handleKey(session, bodyParams)
            "/input/long_tap" -> handleLongTap(session, bodyParams)
            else -> null
        }
    }

    private fun handleTap(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val x = body.optInt("x", -1)
        val y = body.optInt("y", -1)
        if (x < 0 || y < 0) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "x and y required")
        }
        val result = execShell("input tap $x $y")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("action", "tap")
            put("x", x)
            put("y", y)
        })
    }

    private fun handleLongTap(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val x = body.optInt("x", -1)
        val y = body.optInt("y", -1)
        val duration = body.optInt("duration", 1000)
        if (x < 0 || y < 0) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "x and y required")
        }
        val result = execShell("input swipe $x $y $x $y $duration")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("action", "long_tap")
            put("x", x)
            put("y", y)
            put("duration", duration)
        })
    }

    private fun handleSwipe(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val x1 = body.optInt("x1", -1)
        val y1 = body.optInt("y1", -1)
        val x2 = body.optInt("x2", -1)
        val y2 = body.optInt("y2", -1)
        val duration = body.optInt("duration", 300)
        if (x1 < 0 || y1 < 0 || x2 < 0 || y2 < 0) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "x1, y1, x2, y2 required")
        }
        val result = execShell("input swipe $x1 $y1 $x2 $y2 $duration")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("action", "swipe")
        })
    }

    private fun handleText(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val text = body.optString("text", "")
        if (text.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "text required")
        }
        // Escape special characters for shell
        val escaped = text.replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace(" ", "%s")
            .replace("&", "\\&")
            .replace("<", "\\<")
            .replace(">", "\\>")
            .replace("'", "\\'")
        val result = execShell("input text \"$escaped\"")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("action", "text")
            put("text", text)
        })
    }

    private fun handleKey(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val keycode = body.optString("keycode", "")
        if (keycode.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "keycode required")
        }
        val result = execShell("input keyevent $keycode")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("action", "key")
            put("keycode", keycode)
        })
    }
}

data class ShellResult(val output: String, val exitCode: Int)

fun execShell(command: String): ShellResult {
    return try {
        val process = Runtime.getRuntime().exec(arrayOf("sh", "-c", command))
        val output = process.inputStream.bufferedReader().readText()
        val error = process.errorStream.bufferedReader().readText()
        val exitCode = process.waitFor()
        ShellResult(
            output = if (output.isNotEmpty()) output.trim() else error.trim(),
            exitCode = exitCode
        )
    } catch (e: Exception) {
        ShellResult(output = e.message ?: "Unknown error", exitCode = -1)
    }
}
