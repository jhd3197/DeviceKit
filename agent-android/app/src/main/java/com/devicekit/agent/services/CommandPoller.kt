package com.devicekit.agent.services

import android.content.Context
import com.devicekit.agent.LogBuffer
import com.devicekit.agent.api.DeviceKitClient
import com.devicekit.agent.server.SurveyPrimitives
import kotlinx.coroutines.*
import org.json.JSONObject

/**
 * Polls the backend for queued commands and dispatches ONLY read-only survey primitives
 * (plan 25 part 1). This is the device-side enforcement of the trust boundary: a command
 * that is not `survey.<allowlisted-primitive>` is refused with `COMMAND_NOT_ALLOWLISTED`
 * and never executed. The backend composes health/actions from these primitives; it can
 * never push a shell command through this channel.
 *
 * Legacy on-device control (tap, shell over the 9800 HTTP server, `/app/install`) is a
 * separate, locally-reached surface — this poller deliberately does not widen it.
 */
class CommandPoller(
    private val context: Context,
    private val client: DeviceKitClient,
    private val scope: CoroutineScope,
) {
    companion object {
        private const val POLL_INTERVAL_MS = 3_000L
    }

    private var job: Job? = null

    fun start(deviceIdProvider: () -> String?) {
        job?.cancel()
        job = scope.launch {
            while (isActive) {
                val deviceId = deviceIdProvider()
                if (deviceId != null) {
                    try {
                        pollOnce(deviceId)
                    } catch (e: Exception) {
                        LogBuffer.log("CommandPoller", "poll error: ${e.message}", LogBuffer.Level.ERROR)
                    }
                }
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
    }

    private fun pollOnce(deviceId: String) {
        val commands = client.pollCommands(deviceId) ?: return
        for (i in 0 until commands.length()) {
            val cmd = commands.optJSONObject(i) ?: continue
            val id = cmd.optString("id")
            val command = cmd.optString("command")
            val args = cmd.optJSONObject("args") ?: JSONObject()
            if (id.isEmpty() || command.isEmpty()) continue
            dispatch(deviceId, id, command, args)
        }
    }

    private fun dispatch(deviceId: String, id: String, command: String, args: JSONObject) {
        if (!SurveyPrimitives.isSurveyCommand(command)) {
            // The poll channel is read-only-survey-only. Refuse anything else.
            client.postCommandResult(deviceId, id, null, "COMMAND_NOT_ALLOWLISTED")
            LogBuffer.log("CommandPoller", "refused off-list command: $command", LogBuffer.Level.ERROR)
            return
        }
        try {
            val result = SurveyPrimitives.execute(context, command, args)
            client.postCommandResult(deviceId, id, result, null)
        } catch (e: SecurityException) {
            client.postCommandResult(deviceId, id, null, "COMMAND_NOT_ALLOWLISTED")
        } catch (e: Exception) {
            client.postCommandResult(deviceId, id, null, e.message ?: "primitive failed")
        }
    }
}
