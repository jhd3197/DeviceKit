package com.faro.protocol

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import org.json.JSONObject

data class FaroPairing(val code: String, val remainingSecs: Long)

data class FaroPeer(
    val name: String,
    val publicKey: String,
    val fingerprint: String,
    val pairedAt: Long,
)

data class FaroStatus(
    val running: Boolean = false,
    val port: Int = FaroAgentController.DEFAULT_PORT,
    val hostname: String = "",
    val os: String = "",
    val fingerprint: String = "",
    val allowExec: Boolean = true,
    val allowWrite: Boolean = true,
    val peers: List<FaroPeer> = emptyList(),
    val pairing: FaroPairing? = null,
    val error: String? = null,
)

/**
 * Kotlin face of the embedded Faro agent daemon. Owns everything the Rust
 * side can't do itself: the config dir under the app's private storage, the
 * Wi-Fi multicast lock mDNS needs to receive queries, and the prefs that
 * survive process death (enabled flag for boot, device name). Thread-safe;
 * UI polls [status] on a Handler loop.
 */
object FaroAgentController {
    const val DEFAULT_PORT = 8722
    private const val PREFS = "faro_agent"
    private const val KEY_ENABLED = "enabled"
    private const val KEY_DEVICE_NAME = "device_name"

    private var initialized = false
    private var multicastLock: WifiManager.MulticastLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    /** Idempotent; call before anything else (Application/Service onCreate). */
    @Synchronized
    fun init(context: Context) {
        if (initialized) return
        val dir = context.filesDir.resolve("faro-agentd")
        FaroNative.nativeInit(dir.absolutePath, deviceName(context))
        initialized = true
    }

    @Synchronized
    fun start(context: Context): FaroStatus {
        init(context)
        acquireLocks(context)
        prefs(context).edit().putBoolean(KEY_ENABLED, true).apply()
        return parse(FaroNative.nativeSetEnabled(true, DEFAULT_PORT))
    }

    @Synchronized
    fun stop(context: Context): FaroStatus {
        init(context)
        prefs(context).edit().putBoolean(KEY_ENABLED, false).apply()
        val status = parse(FaroNative.nativeSetEnabled(false, 0))
        releaseLocks()
        return status
    }

    fun status(context: Context): FaroStatus {
        init(context)
        return parse(FaroNative.nativeStatus())
    }

    fun openPairing(context: Context): FaroStatus {
        init(context)
        return parse(FaroNative.nativeOpenPairing())
    }

    fun closePairing(context: Context): FaroStatus {
        init(context)
        return parse(FaroNative.nativeClosePairing())
    }

    fun setPolicy(context: Context, allowExec: Boolean, allowWrite: Boolean): FaroStatus {
        init(context)
        return parse(FaroNative.nativeSetPolicy(allowExec, allowWrite))
    }

    fun revokePeer(context: Context, publicKey: String): FaroStatus {
        init(context)
        return parse(FaroNative.nativeRevokePeer(publicKey))
    }

    fun setDeviceName(context: Context, name: String): FaroStatus {
        init(context)
        val trimmed = name.trim()
        prefs(context).edit().putString(KEY_DEVICE_NAME, trimmed).apply()
        return parse(FaroNative.nativeSetDeviceName(trimmed.ifEmpty { Build.MODEL }))
    }

    /** Whether the user left the agent enabled — for BootReceiver / service. */
    fun isEnabled(context: Context): Boolean =
        prefs(context).getBoolean(KEY_ENABLED, false)

    fun deviceName(context: Context): String =
        prefs(context).getString(KEY_DEVICE_NAME, null)?.takeIf { it.isNotBlank() }
            ?: Build.MODEL

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun acquireLocks(context: Context) {
        if (multicastLock != null) return
        val wifi = context.applicationContext
            .getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return
        multicastLock = wifi.createMulticastLock("faro-agent-mdns").apply {
            setReferenceCounted(false)
            acquire()
        }
        wifiLock = wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "faro-agent").apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun releaseLocks() {
        multicastLock?.takeIf { it.isHeld }?.release()
        multicastLock = null
        wifiLock?.takeIf { it.isHeld }?.release()
        wifiLock = null
    }

    private fun parse(json: String): FaroStatus {
        return try {
            val o = JSONObject(json)
            if (o.has("error")) return FaroStatus(error = o.getString("error"))
            FaroStatus(
                running = o.optBoolean("running"),
                port = o.optInt("port", DEFAULT_PORT),
                hostname = o.optString("hostname"),
                os = o.optString("os"),
                fingerprint = o.optString("fingerprint"),
                allowExec = o.optBoolean("allowExec", true),
                allowWrite = o.optBoolean("allowWrite", true),
                peers = o.optJSONArray("peers")?.let { arr ->
                    (0 until arr.length()).map { i ->
                        val p = arr.getJSONObject(i)
                        FaroPeer(
                            name = p.optString("name"),
                            publicKey = p.optString("publicKey"),
                            fingerprint = p.optString("fingerprint"),
                            pairedAt = p.optLong("pairedAt"),
                        )
                    }
                } ?: emptyList(),
                pairing = o.optJSONObject("pairing")?.let {
                    FaroPairing(it.getString("code"), it.optLong("remainingSecs"))
                },
            )
        } catch (e: Exception) {
            FaroStatus(error = "bad status payload: ${e.message}")
        }
    }
}
