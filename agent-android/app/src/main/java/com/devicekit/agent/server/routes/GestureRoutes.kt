package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Gesture recording and replay.
 * Records sequences of input events and replays them.
 */
class GestureRoutes(private val context: Context) : RouteHandler {

    private val gestureDir: File by lazy {
        File(context.filesDir, "gestures").also { it.mkdirs() }
    }

    @Volatile
    private var recording = false
    private val recordedEvents = mutableListOf<GestureEvent>()
    private var recordStartTime = 0L

    data class GestureEvent(
        val type: String,       // tap, swipe, key, wait
        val params: JSONObject,
        val delayMs: Long       // delay from previous event
    )

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            method == NanoHTTPD.Method.POST && uri == "/gesture/record/start" -> handleStartRecord()
            method == NanoHTTPD.Method.POST && uri == "/gesture/record/tap" -> handleRecordTap(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/gesture/record/swipe" -> handleRecordSwipe(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/gesture/record/key" -> handleRecordKey(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/gesture/record/wait" -> handleRecordWait(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/gesture/record/stop" -> handleStopRecord(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/gesture/replay" -> handleReplay(session, bodyParams)
            method == NanoHTTPD.Method.GET && uri == "/gesture/list" -> handleList()
            method == NanoHTTPD.Method.POST && uri == "/gesture/delete" -> handleDelete(session, bodyParams)
            method == NanoHTTPD.Method.GET && uri == "/gesture/get" -> handleGet(session)
            else -> null
        }
    }

    private fun handleStartRecord(): NanoHTTPD.Response {
        recording = true
        recordedEvents.clear()
        recordStartTime = System.currentTimeMillis()
        return jsonResponse(json = JSONObject().apply {
            put("success", true)
            put("status", "recording")
        })
    }

    private fun addEvent(type: String, params: JSONObject): NanoHTTPD.Response {
        if (!recording) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "Not recording. Call /gesture/record/start first.")
        }
        val now = System.currentTimeMillis()
        val delay = if (recordedEvents.isEmpty()) 0 else now - recordStartTime
        recordStartTime = now
        recordedEvents.add(GestureEvent(type, params, delay))
        return jsonResponse(json = JSONObject().apply {
            put("success", true)
            put("event_count", recordedEvents.size)
        })
    }

    private fun handleRecordTap(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        return addEvent("tap", body)
    }

    private fun handleRecordSwipe(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        return addEvent("swipe", body)
    }

    private fun handleRecordKey(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        return addEvent("key", body)
    }

    private fun handleRecordWait(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val ms = body.optLong("ms", 1000)
        return addEvent("wait", JSONObject().apply { put("ms", ms) })
    }

    private fun handleStopRecord(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        recording = false
        val body = parseJsonBody(session, bodyParams)
        val name = body.optString("name", "gesture_${System.currentTimeMillis()}")

        val events = JSONArray()
        recordedEvents.forEach { e ->
            events.put(JSONObject().apply {
                put("type", e.type)
                put("params", e.params)
                put("delay_ms", e.delayMs)
            })
        }

        val gesture = JSONObject().apply {
            put("name", name)
            put("events", events)
            put("event_count", events.length())
            put("created", System.currentTimeMillis())
        }

        // Save to file
        File(gestureDir, "$name.json").writeText(gesture.toString(2))

        val count = recordedEvents.size
        recordedEvents.clear()

        return jsonResponse(json = JSONObject().apply {
            put("success", true)
            put("name", name)
            put("event_count", count)
        })
    }

    private fun handleReplay(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val name = body.optString("name", "")
        val times = body.optInt("times", 1)

        // Load from name or from inline events
        val events: JSONArray = if (name.isNotEmpty()) {
            val file = File(gestureDir, "$name.json")
            if (!file.exists()) {
                return errorResponse(NanoHTTPD.Response.Status.NOT_FOUND, "Gesture not found: $name")
            }
            JSONObject(file.readText()).getJSONArray("events")
        } else if (body.has("events")) {
            body.getJSONArray("events")
        } else {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "name or events required")
        }

        // Replay in background thread
        Thread {
            repeat(times) {
                for (i in 0 until events.length()) {
                    val event = events.getJSONObject(i)
                    val type = event.getString("type")
                    val params = event.getJSONObject("params")
                    val delay = event.optLong("delay_ms", 0)

                    if (delay > 0) Thread.sleep(delay)

                    when (type) {
                        "tap" -> execShell("input tap ${params.getInt("x")} ${params.getInt("y")}")
                        "swipe" -> execShell("input swipe ${params.getInt("x1")} ${params.getInt("y1")} ${params.getInt("x2")} ${params.getInt("y2")} ${params.optInt("duration", 300)}")
                        "key" -> execShell("input keyevent ${params.getString("keycode")}")
                        "wait" -> Thread.sleep(params.optLong("ms", 1000))
                    }
                }
            }
        }.start()

        return jsonResponse(json = JSONObject().apply {
            put("success", true)
            put("replaying", name.ifEmpty { "inline" })
            put("times", times)
            put("event_count", events.length())
        })
    }

    private fun handleList(): NanoHTTPD.Response {
        val gestures = JSONArray()
        gestureDir.listFiles()?.filter { it.extension == "json" }?.forEach { f ->
            try {
                val data = JSONObject(f.readText())
                gestures.put(JSONObject().apply {
                    put("name", data.optString("name", f.nameWithoutExtension))
                    put("event_count", data.optInt("event_count", 0))
                    put("created", data.optLong("created", 0))
                })
            } catch (_: Exception) {}
        }
        return jsonResponse(json = JSONObject().apply {
            put("gestures", gestures)
            put("count", gestures.length())
        })
    }

    private fun handleGet(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val name = session.parms["name"]
            ?: return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "name required")
        val file = File(gestureDir, "$name.json")
        if (!file.exists()) {
            return errorResponse(NanoHTTPD.Response.Status.NOT_FOUND, "Gesture not found: $name")
        }
        return NanoHTTPD.newFixedLengthResponse(
            NanoHTTPD.Response.Status.OK,
            "application/json",
            file.readText()
        )
    }

    private fun handleDelete(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val name = body.optString("name", "")
        if (name.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "name required")
        }
        val file = File(gestureDir, "$name.json")
        val deleted = file.delete()
        return jsonResponse(json = JSONObject().apply {
            put("success", deleted)
            put("name", name)
        })
    }
}
