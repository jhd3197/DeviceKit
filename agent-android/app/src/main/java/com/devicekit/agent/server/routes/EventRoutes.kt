package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.DeviceState
import com.devicekit.agent.server.RouteHandler
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.PipedInputStream
import java.io.PipedOutputStream
import java.io.PrintWriter
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Server-Sent Events (SSE) endpoint for real-time event streaming.
 * Python clients connect to GET /events/stream and receive a continuous
 * stream of events: notifications, keyboard changes, metrics, window changes.
 */
class EventRoutes(private val context: Context) : RouteHandler {

    companion object {
        private val writers = CopyOnWriteArrayList<PrintWriter>()

        /**
         * Broadcast an event to all connected SSE clients.
         * Call from anywhere: EventRoutes.broadcast("notification", jsonData)
         */
        fun broadcast(event: String, data: JSONObject) {
            val message = "event: $event\ndata: ${data.toString()}\n\n"
            val dead = mutableListOf<PrintWriter>()
            for (writer in writers) {
                try {
                    writer.write(message)
                    writer.flush()
                } catch (e: Exception) {
                    dead.add(writer)
                }
            }
            writers.removeAll(dead.toSet())
        }

        fun clientCount(): Int = writers.size
    }

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.GET) return null
        return when (uri) {
            "/events/stream" -> handleStream()
            "/events/clients" -> handleClients()
            else -> null
        }
    }

    private fun handleStream(): NanoHTTPD.Response {
        val pipedOut = PipedOutputStream()
        val pipedIn = PipedInputStream(pipedOut, 8192)
        val writer = PrintWriter(pipedOut, true)

        writers.add(writer)

        // Send initial connection event
        writer.write("event: connected\ndata: {\"status\":\"ok\"}\n\n")
        writer.flush()

        // Start a background thread that sends heartbeats and
        // keeps the connection alive
        Thread {
            try {
                while (true) {
                    Thread.sleep(15_000)
                    writer.write(": keepalive\n\n")
                    writer.flush()
                    if (writer.checkError()) break
                }
            } catch (_: Exception) {
            } finally {
                writers.remove(writer)
                try { writer.close() } catch (_: Exception) {}
                try { pipedOut.close() } catch (_: Exception) {}
            }
        }.also { it.isDaemon = true }.start()

        val response = NanoHTTPD.newChunkedResponse(
            NanoHTTPD.Response.Status.OK,
            "text/event-stream",
            pipedIn
        )
        response.addHeader("Cache-Control", "no-cache")
        response.addHeader("Connection", "keep-alive")
        response.addHeader("Access-Control-Allow-Origin", "*")
        return response
    }

    private fun handleClients(): NanoHTTPD.Response {
        return NanoHTTPD.newFixedLengthResponse(
            NanoHTTPD.Response.Status.OK,
            "application/json",
            JSONObject().apply {
                put("count", writers.size)
            }.toString()
        )
    }
}
