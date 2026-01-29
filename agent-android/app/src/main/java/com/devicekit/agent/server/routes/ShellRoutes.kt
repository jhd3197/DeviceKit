package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject

class ShellRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.POST || uri != "/shell") return null
        return handleShell(session, bodyParams)
    }

    private fun handleShell(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val command = body.optString("command", "")
        val timeout = body.optInt("timeout", 30)
        if (command.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "command required")
        }
        val result = execShellWithTimeout(command, timeout)
        return jsonResponse(json = JSONObject().apply {
            put("output", result.output)
            put("exit_code", result.exitCode)
        })
    }

    private fun execShellWithTimeout(command: String, timeoutSec: Int): ShellResult {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("sh", "-c", command))
            val completed = process.waitFor(timeoutSec.toLong(), java.util.concurrent.TimeUnit.SECONDS)
            if (!completed) {
                process.destroyForcibly()
                return ShellResult("Command timed out after ${timeoutSec}s", -1)
            }
            val output = process.inputStream.bufferedReader().readText()
            val error = process.errorStream.bufferedReader().readText()
            ShellResult(
                output = if (output.isNotEmpty()) output.trim() else error.trim(),
                exitCode = process.exitValue()
            )
        } catch (e: Exception) {
            ShellResult(e.message ?: "Unknown error", -1)
        }
    }
}
