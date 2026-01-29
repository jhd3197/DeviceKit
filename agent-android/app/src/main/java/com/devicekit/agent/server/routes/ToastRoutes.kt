package com.devicekit.agent.server.routes

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject

class ToastRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.POST || uri != "/toast") return null
        return handleToast(session, bodyParams)
    }

    private fun handleToast(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val message = body.optString("message", "")
        val duration = body.optString("duration", "short")

        if (message.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "message required")
        }

        val toastDuration = if (duration == "long") Toast.LENGTH_LONG else Toast.LENGTH_SHORT

        Handler(Looper.getMainLooper()).post {
            Toast.makeText(context, message, toastDuration).show()
        }

        return jsonResponse(json = JSONObject().apply {
            put("success", true)
            put("message", message)
            put("duration", duration)
        })
    }
}
