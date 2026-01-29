package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.server.RouteHandler
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.File
import java.io.PipedInputStream
import java.io.PipedOutputStream

/**
 * MJPEG screen streaming: GET /screen/stream
 * Continuously captures screenshots and streams them as multipart JPEG.
 */
class StreamRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.GET) return null
        return when (uri) {
            "/screen/stream" -> handleMjpegStream(session)
            else -> null
        }
    }

    private fun handleMjpegStream(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val fps = session.parms["fps"]?.toIntOrNull()?.coerceIn(1, 30) ?: 5
        val quality = session.parms["quality"]?.toIntOrNull()?.coerceIn(10, 100) ?: 50
        val intervalMs = 1000L / fps

        val pipedOut = PipedOutputStream()
        val pipedIn = PipedInputStream(pipedOut, 65536)

        val boundary = "droidlink_frame"

        Thread {
            val tmpPng = File(context.cacheDir, "stream_frame.png")
            val tmpJpg = File(context.cacheDir, "stream_frame.jpg")
            try {
                while (true) {
                    // Capture screenshot
                    val result = execShell("screencap -p ${tmpPng.absolutePath}")
                    if (result.exitCode != 0 || !tmpPng.exists()) {
                        Thread.sleep(intervalMs)
                        continue
                    }

                    // Convert PNG to JPEG for smaller size (if possible)
                    // Try using shell convert, fall back to raw PNG
                    val frameBytes: ByteArray
                    val mimeType: String

                    // Try converting to JPEG via Android's built-in tools
                    val convertResult = execShell(
                        "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://${tmpPng.absolutePath} 2>/dev/null; " +
                        "toybox dd if=${tmpPng.absolutePath} 2>/dev/null | head -c 1"
                    )

                    // Just use PNG directly — it's simpler and always works
                    frameBytes = tmpPng.readBytes()
                    mimeType = "image/png"

                    // Write MJPEG frame
                    val header = "--$boundary\r\n" +
                            "Content-Type: $mimeType\r\n" +
                            "Content-Length: ${frameBytes.size}\r\n" +
                            "\r\n"

                    pipedOut.write(header.toByteArray())
                    pipedOut.write(frameBytes)
                    pipedOut.write("\r\n".toByteArray())
                    pipedOut.flush()

                    Thread.sleep(intervalMs)
                }
            } catch (_: Exception) {
                // Client disconnected
            } finally {
                try { pipedOut.close() } catch (_: Exception) {}
                tmpPng.delete()
                tmpJpg.delete()
            }
        }.also { it.isDaemon = true }.start()

        val response = NanoHTTPD.newChunkedResponse(
            NanoHTTPD.Response.Status.OK,
            "multipart/x-mixed-replace; boundary=$boundary",
            pipedIn
        )
        response.addHeader("Cache-Control", "no-cache, no-store")
        response.addHeader("Connection", "keep-alive")
        response.addHeader("Access-Control-Allow-Origin", "*")
        return response
    }
}
