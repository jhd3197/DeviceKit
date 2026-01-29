package com.devicekit.agent.server

import android.content.Context
import android.util.Log
import fi.iki.elonen.NanoHTTPD
import com.devicekit.agent.server.routes.*
import org.json.JSONObject

/**
 * Embedded HTTP server that exposes device control endpoints.
 * Runs on port 9800 inside the agent app, accepting commands from
 * Python (droidlink) via ADB port-forward or direct WiFi connection.
 */
class AgentHttpServer(
    private val context: Context,
    port: Int = DEFAULT_PORT
) : NanoHTTPD(port) {

    companion object {
        private const val TAG = "AgentHttpServer"
        const val DEFAULT_PORT = 9800

        @Volatile
        var instance: AgentHttpServer? = null
            private set
    }

    private val routes = mutableListOf<RouteHandler>()

    init {
        registerRoutes()
    }

    private fun registerRoutes() {
        routes.add(DeviceRoutes(context))
        routes.add(UiRoutes(context))
        routes.add(InputRoutes(context))
        routes.add(ScreenRoutes(context))
        routes.add(FileRoutes(context))
        routes.add(AppRoutes(context))
        routes.add(ShellRoutes(context))
        routes.add(NotificationRoutes(context))
        routes.add(MetricsRoutes(context))
        routes.add(ClipboardRoutes(context))
    }

    override fun start() {
        super.start()
        instance = this
        Log.i(TAG, "HTTP server started on port $listeningPort")
    }

    override fun stop() {
        instance = null
        super.stop()
        Log.i(TAG, "HTTP server stopped")
    }

    override fun serve(session: IHTTPSession): Response {
        val uri = session.uri.trimEnd('/')
        val method = session.method

        Log.d(TAG, "${method.name} $uri")

        // Parse body for POST/PUT
        val bodyParams = mutableMapOf<String, String>()
        if (method == Method.POST || method == Method.PUT) {
            try {
                session.parseBody(bodyParams)
            } catch (e: Exception) {
                Log.w(TAG, "Failed to parse body: ${e.message}")
            }
        }

        // Try each route handler
        for (handler in routes) {
            val response = handler.handle(method, uri, session, bodyParams)
            if (response != null) {
                return response.also {
                    it.addHeader("Access-Control-Allow-Origin", "*")
                }
            }
        }

        return jsonResponse(Response.Status.NOT_FOUND, JSONObject().apply {
            put("error", "Not found")
            put("path", uri)
            put("method", method.name)
        })
    }
}

/** Base interface for route handlers */
interface RouteHandler {
    fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response?
}

/** Helper to create a JSON response */
fun jsonResponse(
    status: NanoHTTPD.Response.Status = NanoHTTPD.Response.Status.OK,
    json: JSONObject
): NanoHTTPD.Response {
    return NanoHTTPD.newFixedLengthResponse(
        status,
        "application/json",
        json.toString()
    )
}

/** Helper to parse JSON body from session */
fun parseJsonBody(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): JSONObject {
    val postData = bodyParams["postData"]
    if (!postData.isNullOrBlank()) {
        return try {
            JSONObject(postData)
        } catch (e: Exception) {
            JSONObject()
        }
    }
    return JSONObject()
}

/** Helper for error responses */
fun errorResponse(
    status: NanoHTTPD.Response.Status = NanoHTTPD.Response.Status.INTERNAL_ERROR,
    message: String
): NanoHTTPD.Response {
    return jsonResponse(status, JSONObject().apply {
        put("error", message)
    })
}
