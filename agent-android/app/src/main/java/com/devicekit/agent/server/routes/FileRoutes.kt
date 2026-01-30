package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.File

class FileRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            method == NanoHTTPD.Method.GET && uri == "/files/list" -> handleList(session)
            method == NanoHTTPD.Method.GET && uri == "/files/read" -> handleRead(session)
            method == NanoHTTPD.Method.GET && uri == "/files/search" -> handleSearch(session)
            method == NanoHTTPD.Method.POST && uri == "/files/write" -> handleWrite(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/files/mkdir" -> handleMkdir(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/files/delete" -> handleDelete(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/files/rename" -> handleRename(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/files/upload" -> handleUpload(session, bodyParams)
            else -> null
        }
    }

    private fun handleList(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val path = session.parms["path"] ?: "/sdcard"
        val file = File(path)
        if (!file.exists() || !file.isDirectory) {
            return errorResponse(NanoHTTPD.Response.Status.NOT_FOUND, "Directory not found: $path")
        }
        val items = JSONArray()
        file.listFiles()?.sortedWith(compareBy({ !it.isDirectory }, { it.name.lowercase() }))?.forEach { f ->
            items.put(JSONObject().apply {
                put("name", f.name)
                put("path", f.absolutePath)
                put("is_dir", f.isDirectory)
                put("size", if (f.isFile) f.length() else 0)
                put("modified", f.lastModified())
                put("readable", f.canRead())
                put("writable", f.canWrite())
            })
        }
        return jsonResponse(json = JSONObject().apply {
            put("path", path)
            put("items", items)
            put("count", items.length())
        })
    }

    private fun handleRead(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val path = session.parms["path"]
            ?: return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "path required")
        val file = File(path)
        if (!file.exists()) {
            return errorResponse(NanoHTTPD.Response.Status.NOT_FOUND, "File not found: $path")
        }
        if (!file.isFile) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "Not a file: $path")
        }
        val bytes = file.readBytes()
        val mimeType = guessMimeType(file.name)
        return NanoHTTPD.newFixedLengthResponse(
            NanoHTTPD.Response.Status.OK,
            mimeType,
            ByteArrayInputStream(bytes),
            bytes.size.toLong()
        )
    }

    private fun handleWrite(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val path = body.optString("path", "")
        val content = body.optString("content", "")
        if (path.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "path required")
        }
        return try {
            val file = File(path)
            file.parentFile?.mkdirs()
            file.writeText(content)
            jsonResponse(json = JSONObject().apply {
                put("success", true)
                put("path", path)
                put("size", file.length())
            })
        } catch (e: Exception) {
            errorResponse(message = "Write failed: ${e.message}")
        }
    }

    private fun handleMkdir(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val path = body.optString("path", "")
        if (path.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "path required")
        }
        val file = File(path)
        val created = file.mkdirs()
        return jsonResponse(json = JSONObject().apply {
            put("success", created || file.exists())
            put("path", path)
        })
    }

    private fun handleDelete(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val path = body.optString("path", "")
        if (path.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "path required")
        }
        val file = File(path)
        if (!file.exists()) {
            return errorResponse(NanoHTTPD.Response.Status.NOT_FOUND, "Not found: $path")
        }
        val deleted = if (file.isDirectory) file.deleteRecursively() else file.delete()
        return jsonResponse(json = JSONObject().apply {
            put("success", deleted)
            put("path", path)
        })
    }

    private fun handleRename(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val from = body.optString("from", "")
        val to = body.optString("to", "")
        if (from.isEmpty() || to.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "from and to required")
        }
        val source = File(from)
        if (!source.exists()) {
            return errorResponse(NanoHTTPD.Response.Status.NOT_FOUND, "Not found: $from")
        }
        val renamed = source.renameTo(File(to))
        return jsonResponse(json = JSONObject().apply {
            put("success", renamed)
            put("from", from)
            put("to", to)
        })
    }

    private fun handleSearch(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val query = session.parms["query"]
            ?: return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "query required")
        val rootPath = session.parms["path"] ?: "/sdcard"
        val limit = (session.parms["limit"] ?: "50").toIntOrNull() ?: 50
        val maxDepth = 10

        val root = File(rootPath)
        if (!root.exists() || !root.isDirectory) {
            return errorResponse(NanoHTTPD.Response.Status.NOT_FOUND, "Directory not found: $rootPath")
        }

        val queryLower = query.lowercase()
        val results = JSONArray()

        fun walk(dir: File, depth: Int) {
            if (depth > maxDepth || results.length() >= limit) return
            val children = dir.listFiles() ?: return
            for (f in children) {
                if (results.length() >= limit) return
                if (f.name.lowercase().contains(queryLower)) {
                    results.put(JSONObject().apply {
                        put("name", f.name)
                        put("path", f.absolutePath)
                        put("is_dir", f.isDirectory)
                        put("size", if (f.isFile) f.length() else 0)
                        put("modified", f.lastModified())
                    })
                }
                if (f.isDirectory) {
                    walk(f, depth + 1)
                }
            }
        }

        walk(root, 0)

        return jsonResponse(json = JSONObject().apply {
            put("query", query)
            put("root", rootPath)
            put("results", results)
            put("count", results.length())
            put("limit", limit)
        })
    }

    private fun handleUpload(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val targetPath = session.parms["path"]
            ?: return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "path query parameter required")

        // NanoHTTPD stores uploaded file content in a temp file, path available in bodyParams
        val tempFilePath = bodyParams["file"]
            ?: return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "multipart 'file' field required")

        return try {
            val tempFile = File(tempFilePath)
            val targetFile = File(targetPath)
            targetFile.parentFile?.mkdirs()
            tempFile.copyTo(targetFile, overwrite = true)
            tempFile.delete()
            jsonResponse(json = JSONObject().apply {
                put("success", true)
                put("path", targetFile.absolutePath)
                put("size", targetFile.length())
            })
        } catch (e: Exception) {
            errorResponse(message = "Upload failed: ${e.message}")
        }
    }

    private fun guessMimeType(name: String): String {
        return when {
            name.endsWith(".json") -> "application/json"
            name.endsWith(".txt") || name.endsWith(".log") -> "text/plain"
            name.endsWith(".html") -> "text/html"
            name.endsWith(".xml") -> "application/xml"
            name.endsWith(".png") -> "image/png"
            name.endsWith(".jpg") || name.endsWith(".jpeg") -> "image/jpeg"
            name.endsWith(".gif") -> "image/gif"
            name.endsWith(".mp4") -> "video/mp4"
            name.endsWith(".mp3") -> "audio/mpeg"
            name.endsWith(".apk") -> "application/vnd.android.package-archive"
            else -> "application/octet-stream"
        }
    }
}
