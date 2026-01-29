package com.devicekit.agent.server.routes

import android.content.Context
import android.content.Intent
import android.net.Uri
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject

/**
 * Intent firing: broadcast, start activity, start service.
 */
class IntentRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.POST) return null
        return when (uri) {
            "/intent/broadcast" -> handleBroadcast(session, bodyParams)
            "/intent/start" -> handleStartActivity(session, bodyParams)
            "/intent/service" -> handleStartService(session, bodyParams)
            "/intent/open_url" -> handleOpenUrl(session, bodyParams)
            else -> null
        }
    }

    private fun handleBroadcast(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val action = body.optString("action", "")
        if (action.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "action required")
        }

        return try {
            val intent = buildIntent(action, body)
            context.sendBroadcast(intent)
            jsonResponse(json = JSONObject().apply {
                put("success", true)
                put("type", "broadcast")
                put("action", action)
            })
        } catch (e: Exception) {
            errorResponse(message = "Broadcast failed: ${e.message}")
        }
    }

    private fun handleStartActivity(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val action = body.optString("action", "")
        val component = body.optString("component", "")

        if (action.isEmpty() && component.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "action or component required")
        }

        return try {
            // Use am start for more reliable activity launching
            val cmd = buildAmCommand("start", body)
            val result = execShell(cmd)
            jsonResponse(json = JSONObject().apply {
                put("success", result.exitCode == 0)
                put("type", "activity")
                put("output", result.output)
            })
        } catch (e: Exception) {
            errorResponse(message = "Start activity failed: ${e.message}")
        }
    }

    private fun handleStartService(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        return try {
            val cmd = buildAmCommand("startservice", body)
            val result = execShell(cmd)
            jsonResponse(json = JSONObject().apply {
                put("success", result.exitCode == 0)
                put("type", "service")
                put("output", result.output)
            })
        } catch (e: Exception) {
            errorResponse(message = "Start service failed: ${e.message}")
        }
    }

    private fun handleOpenUrl(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val url = body.optString("url", "")
        if (url.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "url required")
        }

        return try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            jsonResponse(json = JSONObject().apply {
                put("success", true)
                put("url", url)
            })
        } catch (e: Exception) {
            errorResponse(message = "Open URL failed: ${e.message}")
        }
    }

    private fun buildIntent(action: String, body: JSONObject): Intent {
        val intent = Intent(action)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        body.optString("data", "").takeIf { it.isNotEmpty() }?.let {
            intent.data = Uri.parse(it)
        }
        body.optString("type", "").takeIf { it.isNotEmpty() }?.let {
            intent.type = it
        }
        body.optString("package", "").takeIf { it.isNotEmpty() }?.let {
            intent.setPackage(it)
        }

        // Add extras
        body.optJSONObject("extras")?.let { extras ->
            for (key in extras.keys()) {
                when (val value = extras.get(key)) {
                    is String -> intent.putExtra(key, value)
                    is Int -> intent.putExtra(key, value)
                    is Long -> intent.putExtra(key, value)
                    is Double -> intent.putExtra(key, value)
                    is Boolean -> intent.putExtra(key, value)
                }
            }
        }

        return intent
    }

    private fun buildAmCommand(verb: String, body: JSONObject): String {
        val parts = mutableListOf("am", verb)

        body.optString("action", "").takeIf { it.isNotEmpty() }?.let {
            parts.add("-a"); parts.add(it)
        }
        body.optString("data", "").takeIf { it.isNotEmpty() }?.let {
            parts.add("-d"); parts.add("\"$it\"")
        }
        body.optString("type", "").takeIf { it.isNotEmpty() }?.let {
            parts.add("-t"); parts.add(it)
        }
        body.optString("component", "").takeIf { it.isNotEmpty() }?.let {
            parts.add("-n"); parts.add(it)
        }
        body.optString("package", "").takeIf { it.isNotEmpty() }?.let {
            parts.add("-p"); parts.add(it)
        }
        body.optString("category", "").takeIf { it.isNotEmpty() }?.let {
            parts.add("-c"); parts.add(it)
        }

        // Extras
        body.optJSONObject("extras")?.let { extras ->
            for (key in extras.keys()) {
                when (val value = extras.get(key)) {
                    is String -> { parts.add("--es"); parts.add(key); parts.add("\"$value\"") }
                    is Int -> { parts.add("--ei"); parts.add(key); parts.add(value.toString()) }
                    is Long -> { parts.add("--el"); parts.add(key); parts.add(value.toString()) }
                    is Boolean -> { parts.add("--ez"); parts.add(key); parts.add(value.toString()) }
                    is Double -> { parts.add("--ef"); parts.add(key); parts.add(value.toString()) }
                }
            }
        }

        return parts.joinToString(" ")
    }
}
