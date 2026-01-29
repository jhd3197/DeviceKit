package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.DeviceState
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject

class NotificationRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            method == NanoHTTPD.Method.GET && uri == "/notifications" -> handleList()
            method == NanoHTTPD.Method.POST && uri == "/notifications/clear" -> handleClear()
            else -> null
        }
    }

    private fun handleList(): NanoHTTPD.Response {
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

    private fun handleClear(): NanoHTTPD.Response {
        DeviceState.clearNotifications()
        return jsonResponse(json = JSONObject().apply {
            put("success", true)
        })
    }
}
