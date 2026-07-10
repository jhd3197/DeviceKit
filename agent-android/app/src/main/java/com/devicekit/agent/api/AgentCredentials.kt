package com.devicekit.agent.api

import android.content.Context
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Per-device HMAC credentials issued by the DeviceKit backend at enrollment (plan 07).
 *
 * The secret is stored in private SharedPreferences and used to sign every request to the
 * backend: `HMAC-SHA256(secret, "deviceId:timestamp:nonce")`. Until a secret is present the
 * agent talks to the backend unsigned (legacy / auth-disabled dev mode); once paired, all
 * requests carry the `X-Agent-*` headers the panel verifies before consuming the nonce.
 */
object AgentCredentials {

    private const val PREFS = "devicekit_agent_creds"
    private const val KEY_SECRET = "hmac_secret"
    private const val KEY_DEVICE_ID = "device_id"

    private val rng = SecureRandom()

    @Volatile private var secret: String? = null
    @Volatile var deviceId: String? = null
        private set

    fun init(context: Context) {
        val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        secret = prefs.getString(KEY_SECRET, null)
        deviceId = prefs.getString(KEY_DEVICE_ID, null)
    }

    fun save(context: Context, deviceId: String, secret: String) {
        this.deviceId = deviceId
        this.secret = secret
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_DEVICE_ID, deviceId)
            .putString(KEY_SECRET, secret)
            .apply()
    }

    fun clear(context: Context) {
        secret = null
        deviceId = null
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().clear().apply()
    }

    fun isEnrolled(): Boolean = !secret.isNullOrEmpty()

    fun newNonce(): String {
        val bytes = ByteArray(16)
        rng.nextBytes(bytes)
        return bytes.joinToString("") { "%02x".format(it) }
    }

    /**
     * Compute the request signature for a given device id. Returns null when no secret is
     * stored (the caller then sends the request unsigned).
     */
    fun sign(deviceId: String, timestamp: String, nonce: String): String? {
        val key = secret ?: return null
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key.toByteArray(), "HmacSHA256"))
        val raw = mac.doFinal("$deviceId:$timestamp:$nonce".toByteArray())
        return raw.joinToString("") { "%02x".format(it) }
    }
}
