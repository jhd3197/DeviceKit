package com.devicekit.agent.server

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import android.util.Log
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/**
 * UDP broadcast responder for WiFi auto-discovery.
 * Listens on port 9801 for discovery probes and responds with device info.
 *
 * Python side sends "DROIDLINK_DISCOVER" to broadcast address,
 * this service responds with JSON containing device info and HTTP port.
 */
class DiscoveryService(private val context: Context) {

    companion object {
        private const val TAG = "DiscoveryService"
        const val DISCOVERY_PORT = 9801
        const val DISCOVERY_PROBE = "DROIDLINK_DISCOVER"
        const val DISCOVERY_RESPONSE_PREFIX = "DROIDLINK_DEVICE:"
    }

    @Volatile
    private var running = false
    private var thread: Thread? = null

    fun start() {
        if (running) return
        running = true
        thread = Thread {
            runDiscoveryLoop()
        }.also {
            it.isDaemon = true
            it.name = "droidlink-discovery"
            it.start()
        }
        Log.i(TAG, "Discovery service started on port $DISCOVERY_PORT")
    }

    fun stop() {
        running = false
        thread?.interrupt()
        thread = null
        Log.i(TAG, "Discovery service stopped")
    }

    private fun runDiscoveryLoop() {
        var socket: DatagramSocket? = null
        try {
            socket = DatagramSocket(DISCOVERY_PORT)
            socket.broadcast = true
            socket.soTimeout = 5000  // 5s timeout to check running flag

            val buffer = ByteArray(256)
            val responseData = buildResponse()

            while (running) {
                try {
                    val packet = DatagramPacket(buffer, buffer.size)
                    socket.receive(packet)

                    val message = String(packet.data, 0, packet.length).trim()
                    if (message == DISCOVERY_PROBE) {
                        Log.d(TAG, "Discovery probe from ${packet.address.hostAddress}:${packet.port}")

                        val responseBytes = responseData.toByteArray()
                        val responsePacket = DatagramPacket(
                            responseBytes,
                            responseBytes.size,
                            packet.address,
                            packet.port
                        )
                        socket.send(responsePacket)
                    }
                } catch (e: java.net.SocketTimeoutException) {
                    // Normal timeout, loop continues
                } catch (e: Exception) {
                    if (running) {
                        Log.w(TAG, "Discovery error: ${e.message}")
                        Thread.sleep(1000)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Discovery service failed: ${e.message}")
        } finally {
            socket?.close()
        }
    }

    private fun buildResponse(): String {
        val ip = getWifiIpAddress()
        val info = JSONObject().apply {
            put("model", Build.MODEL)
            put("manufacturer", Build.MANUFACTURER)
            put("sdk", Build.VERSION.SDK_INT)
            put("android_version", Build.VERSION.RELEASE)
            put("device", Build.DEVICE)
            put("ip", ip)
            put("port", AgentHttpServer.DEFAULT_PORT)
            put("agent", "devicekit")
            put("version", "1.0.0")
        }
        return DISCOVERY_RESPONSE_PREFIX + info.toString()
    }

    private fun getWifiIpAddress(): String {
        return try {
            val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            @Suppress("DEPRECATION")
            val ip = wifiManager.connectionInfo.ipAddress
            if (ip == 0) return "0.0.0.0"
            String.format(
                "%d.%d.%d.%d",
                ip and 0xff,
                (ip shr 8) and 0xff,
                (ip shr 16) and 0xff,
                (ip shr 24) and 0xff
            )
        } catch (e: Exception) {
            "0.0.0.0"
        }
    }
}
