package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject
import java.io.PipedInputStream
import java.io.PipedOutputStream

/**
 * Logcat access: dump recent logs or stream live.
 */
class LogcatRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            method == NanoHTTPD.Method.GET && uri == "/logcat" -> handleDump(session)
            method == NanoHTTPD.Method.GET && uri == "/logcat/stream" -> handleStream(session)
            method == NanoHTTPD.Method.POST && uri == "/logcat/clear" -> handleClear()
            else -> null
        }
    }

    private fun handleDump(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val lines = session.parms["lines"]?.toIntOrNull() ?: 100
        val filter = session.parms["filter"] ?: ""
        val level = session.parms["level"] ?: ""

        var cmd = "logcat -d -t $lines"
        if (level.isNotEmpty()) {
            cmd += " *:${level.uppercase()}"
        }
        if (filter.isNotEmpty()) {
            cmd += " | grep -i \"$filter\""
        }

        val result = execShell(cmd)
        val logLines = result.output.lines().filter { it.isNotBlank() }

        return jsonResponse(json = JSONObject().apply {
            put("lines", JSONArray(logLines))
            put("count", logLines.size)
        })
    }

    private fun handleStream(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val filter = session.parms["filter"] ?: ""
        val level = session.parms["level"] ?: ""

        var cmd = "logcat"
        if (level.isNotEmpty()) {
            cmd += " *:${level.uppercase()}"
        }

        val pipedOut = PipedOutputStream()
        val pipedIn = PipedInputStream(pipedOut, 16384)

        Thread {
            var process: Process? = null
            try {
                process = Runtime.getRuntime().exec(arrayOf("sh", "-c", cmd))
                val reader = process.inputStream.bufferedReader()
                var line: String?
                while (reader.readLine().also { line = it } != null) {
                    val l = line ?: continue
                    if (filter.isNotEmpty() && !l.contains(filter, ignoreCase = true)) continue

                    val sseMsg = "data: ${l.replace("\\", "\\\\").replace("\"", "\\\"")}\n\n"
                    pipedOut.write(sseMsg.toByteArray())
                    pipedOut.flush()
                }
            } catch (_: Exception) {
                // Client disconnected
            } finally {
                process?.destroyForcibly()
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
        return response
    }

    private fun handleClear(): NanoHTTPD.Response {
        val result = execShell("logcat -c")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
        })
    }
}
