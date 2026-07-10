package com.devicekit.agent.api

import com.devicekit.agent.DeviceState
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * HTTP client that communicates with the DeviceKit backend server.
 * Reports device state, receives commands, and maintains heartbeat.
 *
 * Plan 07: when the device is enrolled ([AgentCredentials.isEnrolled]) every request is
 * signed with `X-Agent-Timestamp` / `X-Agent-Nonce` / `X-Agent-Signature` headers over
 * `deviceId:timestamp:nonce`, which the panel verifies before consuming the nonce. Requests
 * stay unsigned until pairing completes, so the auth-disabled dev flow is unaffected.
 */
class DeviceKitClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .build()

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    private val baseUrl: String
        get() = DeviceState.serverUrl.trimEnd('/')

    /** Attach signed auth headers for [deviceId] if a per-device secret is stored. */
    private fun Request.Builder.signed(deviceId: String?): Request.Builder {
        if (deviceId == null || !AgentCredentials.isEnrolled()) return this
        val timestamp = (System.currentTimeMillis() / 1000.0).toString()
        val nonce = AgentCredentials.newNonce()
        val sig = AgentCredentials.sign(deviceId, timestamp, nonce) ?: return this
        header("X-Agent-Timestamp", timestamp)
        header("X-Agent-Nonce", nonce)
        header("X-Agent-Signature", sig)
        return this
    }

    /**
     * Register this device with the DeviceKit server.
     * Returns the device ID assigned by the server, or null on failure.
     */
    fun register(deviceInfo: JSONObject): String? {
        return try {
            val derivedId = deviceInfo.optString("manufacturer") + "_" + deviceInfo.optString("model")
            val body = deviceInfo.toString().toRequestBody(jsonMediaType)
            val request = Request.Builder()
                .url("$baseUrl/agent-device/register")
                .post(body)
                .signed(derivedId.replace(" ", "_"))
                .build()
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    val json = JSONObject(response.body?.string() ?: "{}")
                    json.optString("device_id", null)
                } else null
            }
        } catch (e: IOException) {
            null
        }
    }

    /**
     * Push current device state to the server.
     */
    fun reportState(state: JSONObject): Boolean {
        return try {
            val body = state.toString().toRequestBody(jsonMediaType)
            val request = Request.Builder()
                .url("$baseUrl/agent-device/state")
                .post(body)
                .signed(state.optString("device_id", DeviceState.deviceId))
                .build()
            client.newCall(request).execute().use { it.isSuccessful }
        } catch (e: IOException) {
            false
        }
    }

    /**
     * Send heartbeat to keep the connection alive.
     */
    fun heartbeat(deviceId: String): Boolean {
        return try {
            val body = JSONObject().apply {
                put("device_id", deviceId)
                put("timestamp", System.currentTimeMillis())
            }.toString().toRequestBody(jsonMediaType)

            val request = Request.Builder()
                .url("$baseUrl/agent-device/heartbeat")
                .post(body)
                .signed(deviceId)
                .build()
            client.newCall(request).execute().use { it.isSuccessful }
        } catch (e: IOException) {
            false
        }
    }

    /**
     * Poll for pending commands from the server. Returns the list of queued commands
     * (each `{id, command, args}`), or null on failure.
     */
    fun pollCommands(deviceId: String): org.json.JSONArray? {
        return try {
            val request = Request.Builder()
                .url("$baseUrl/agent-device/$deviceId/commands")
                .get()
                .signed(deviceId)
                .build()
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    val json = JSONObject(response.body?.string() ?: "{}")
                    json.optJSONArray("commands")
                } else null
            }
        } catch (e: IOException) {
            null
        }
    }

    /**
     * Post the result of a dispatched command back to the server so the waiting caller
     * unblocks (plan 07 synchronous dispatch).
     */
    fun postCommandResult(deviceId: String, commandId: String, result: JSONObject?, error: String?): Boolean {
        return try {
            val payload = JSONObject().apply {
                put("device_id", deviceId)
                put("command_id", commandId)
                if (result != null) put("result", result)
                if (error != null) put("error", error)
            }
            val body = payload.toString().toRequestBody(jsonMediaType)
            val request = Request.Builder()
                .url("$baseUrl/agent-device/command-result")
                .post(body)
                .signed(deviceId)
                .build()
            client.newCall(request).execute().use { it.isSuccessful }
        } catch (e: IOException) {
            false
        }
    }

    /**
     * Report a specific event (keyboard shown, notification received, etc.)
     */
    fun reportEvent(deviceId: String, eventType: String, data: JSONObject): Boolean {
        return try {
            val payload = JSONObject().apply {
                put("device_id", deviceId)
                put("event", eventType)
                put("data", data)
                put("timestamp", System.currentTimeMillis())
            }
            val body = payload.toString().toRequestBody(jsonMediaType)
            val request = Request.Builder()
                .url("$baseUrl/agent-device/event")
                .post(body)
                .signed(deviceId)
                .build()
            client.newCall(request).execute().use { it.isSuccessful }
        } catch (e: IOException) {
            false
        }
    }

    // ---------------------------------------------------------------------
    // Pairing / enrollment (plan 07 phase 3)
    // ---------------------------------------------------------------------

    /**
     * Begin enrollment: send device info, receive a `{pairing_id, code, expires_at}` the
     * agent displays for an operator to claim from the dashboard. Returns null on failure.
     */
    fun enroll(deviceInfo: JSONObject): JSONObject? {
        return try {
            val body = deviceInfo.toString().toRequestBody(jsonMediaType)
            val request = Request.Builder()
                .url("$baseUrl/agent-device/enroll")
                .post(body)
                .build()
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) JSONObject(response.body?.string() ?: "{}") else null
            }
        } catch (e: IOException) {
            null
        }
    }

    /**
     * Poll enrollment status. Once an operator claims the code the response carries
     * `{claimed: true, device_id, secret}` exactly once — the agent stores the secret and
     * switches to signed requests. Returns null on failure.
     */
    fun pollEnrollment(pairingId: String): JSONObject? {
        return try {
            val request = Request.Builder()
                .url("$baseUrl/agent-device/enroll/$pairingId")
                .get()
                .build()
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) JSONObject(response.body?.string() ?: "{}") else null
            }
        } catch (e: IOException) {
            null
        }
    }

    /**
     * Check if the server is reachable.
     */
    fun ping(): Boolean {
        return try {
            val request = Request.Builder()
                .url("$baseUrl/health")
                .get()
                .build()
            client.newCall(request).execute().use { it.isSuccessful }
        } catch (e: IOException) {
            false
        }
    }
}
