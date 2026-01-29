package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject

/**
 * Contacts and SMS reading via content provider / shell commands.
 */
class ContactRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            method == NanoHTTPD.Method.GET && uri == "/contacts" -> handleListContacts(session)
            method == NanoHTTPD.Method.GET && uri == "/contacts/search" -> handleSearchContacts(session)
            method == NanoHTTPD.Method.GET && uri == "/sms" -> handleListSms(session)
            method == NanoHTTPD.Method.GET && uri == "/sms/conversations" -> handleConversations(session)
            else -> null
        }
    }

    private fun handleListContacts(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val limit = session.parms["limit"]?.toIntOrNull() ?: 100

        // Use content command to query contacts provider
        val result = execShell(
            "content query --uri content://com.android.contacts/contacts " +
            "--projection display_name:_id:has_phone_number " +
            "| head -n $limit"
        )

        val contacts = parseContentOutput(result.output)
        return jsonResponse(json = JSONObject().apply {
            put("contacts", contacts)
            put("count", contacts.length())
        })
    }

    private fun handleSearchContacts(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val query = session.parms["q"]
            ?: return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "q required")

        val result = execShell(
            "content query --uri content://com.android.contacts/contacts " +
            "--projection display_name:_id:has_phone_number " +
            "--where \"display_name LIKE '%$query%'\""
        )

        val contacts = parseContentOutput(result.output)
        return jsonResponse(json = JSONObject().apply {
            put("query", query)
            put("contacts", contacts)
            put("count", contacts.length())
        })
    }

    private fun handleListSms(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val limit = session.parms["limit"]?.toIntOrNull() ?: 50
        val address = session.parms["address"] ?: ""

        var cmd = "content query --uri content://sms " +
                "--projection address:body:date:type " +
                "--sort \"date DESC\""
        if (address.isNotEmpty()) {
            cmd += " --where \"address='$address'\""
        }
        cmd += " | head -n $limit"

        val result = execShell(cmd)
        val messages = parseContentOutput(result.output)

        return jsonResponse(json = JSONObject().apply {
            put("messages", messages)
            put("count", messages.length())
        })
    }

    private fun handleConversations(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val limit = session.parms["limit"]?.toIntOrNull() ?: 20

        val result = execShell(
            "content query --uri content://sms " +
            "--projection address:body:date " +
            "--sort \"date DESC\" | head -n $limit"
        )

        // Group by address for conversations
        val messages = parseContentOutput(result.output)
        val conversations = mutableMapOf<String, JSONObject>()

        for (i in 0 until messages.length()) {
            val msg = messages.getJSONObject(i)
            val addr = msg.optString("address", "unknown")
            if (addr !in conversations) {
                conversations[addr] = JSONObject().apply {
                    put("address", addr)
                    put("last_message", msg.optString("body", ""))
                    put("last_date", msg.optString("date", ""))
                    put("message_count", 1)
                }
            } else {
                val conv = conversations[addr]!!
                conv.put("message_count", conv.getInt("message_count") + 1)
            }
        }

        val convArray = JSONArray()
        conversations.values.forEach { convArray.put(it) }

        return jsonResponse(json = JSONObject().apply {
            put("conversations", convArray)
            put("count", convArray.length())
        })
    }

    /**
     * Parse output from `content query` command.
     * Format: Row: 0 key1=value1, key2=value2
     */
    private fun parseContentOutput(output: String): JSONArray {
        val results = JSONArray()
        for (line in output.lines()) {
            if (!line.startsWith("Row:")) continue
            val obj = JSONObject()
            // Remove "Row: N " prefix
            val data = line.substringAfter(" ", "").substringAfter(" ", "")
            for (pair in data.split(", ")) {
                val eq = pair.indexOf('=')
                if (eq > 0) {
                    val key = pair.substring(0, eq).trim()
                    val value = pair.substring(eq + 1).trim()
                    obj.put(key, value)
                }
            }
            if (obj.length() > 0) {
                results.put(obj)
            }
        }
        return results
    }
}
