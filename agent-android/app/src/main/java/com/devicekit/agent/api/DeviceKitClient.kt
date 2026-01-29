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

    /**
     * Register this device with the DeviceKit server.
     * Returns the device ID assigned by the server, or null on failure.
     */
    fun register(deviceInfo: JSONObject): String? {
        return try {
            val body = deviceInfo.toString().toRequestBody(jsonMediaType)
            val request = Request.Builder()
                .url("$baseUrl/agent-device/register")
                .post(body)
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
                .build()
            client.newCall(request).execute().use { it.isSuccessful }
        } catch (e: IOException) {
            false
        }
    }

    /**
     * Poll for pending commands from the server.
     * Returns a JSON command object or null.
     */
    fun pollCommands(deviceId: String): JSONObject? {
        return try {
            val request = Request.Builder()
                .url("$baseUrl/agent-device/$deviceId/commands")
                .get()
                .build()
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    val json = JSONObject(response.body?.string() ?: "{}")
                    if (json.has("command")) json else null
                } else null
            }
        } catch (e: IOException) {
            null
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
                .build()
            client.newCall(request).execute().use { it.isSuccessful }
        } catch (e: IOException) {
            false
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
