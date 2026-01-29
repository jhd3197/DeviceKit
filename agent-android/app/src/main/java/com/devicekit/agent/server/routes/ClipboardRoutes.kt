package com.devicekit.agent.server.routes

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Handler
import android.os.Looper
import com.devicekit.agent.DeviceState
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class ClipboardRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            method == NanoHTTPD.Method.GET && uri == "/clipboard" -> handleGet()
            method == NanoHTTPD.Method.POST && uri == "/clipboard" -> handleSet(session, bodyParams)
            else -> null
        }
    }

    private fun handleGet(): NanoHTTPD.Response {
        var text: String? = DeviceState.lastClipboardText
        // Try to read from system clipboard on main thread
        val latch = CountDownLatch(1)
        Handler(Looper.getMainLooper()).post {
            try {
                val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                if (cm.hasPrimaryClip()) {
                    text = cm.primaryClip?.getItemAt(0)?.text?.toString()
                }
            } catch (_: Exception) {
                // Fall back to DeviceState
            }
            latch.countDown()
        }
        latch.await(2, TimeUnit.SECONDS)

        return jsonResponse(json = JSONObject().apply {
            put("text", text)
        })
    }

    private fun handleSet(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val text = body.optString("text", "")
        if (text.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "text required")
        }

        val latch = CountDownLatch(1)
        var success = false
        Handler(Looper.getMainLooper()).post {
            try {
                val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("droidlink", text))
                DeviceState.lastClipboardText = text
                success = true
            } catch (_: Exception) {
                // fallback
            }
            latch.countDown()
        }
        latch.await(2, TimeUnit.SECONDS)

        return jsonResponse(json = JSONObject().apply {
            put("success", success)
            put("text", text)
        })
    }
}
