package com.devicekit.agent.services

import android.content.Context
import com.devicekit.agent.BuildConfig
import com.devicekit.agent.LogBuffer
import com.devicekit.agent.api.DeviceKitClient
import com.devicekit.agent.server.routes.execShell
import kotlinx.coroutines.*
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters
import org.bouncycastle.crypto.signers.Ed25519Signer
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/**
 * OTA self-update loop (plan 25 phase 3). Every [CHECK_INTERVAL_MS] this asks the backend whether
 * a newer agent build is being rolled out to this device and, if so, verifies + downloads + installs
 * it, reporting each step back to the panel.
 *
 * Trust model: the offered manifest carries an Ed25519 signature over the canonical JSON of its 5
 * fields. We verify that signature against a PINNED public key baked in at build time
 * ([BuildConfig.OTA_PUBLIC_KEY]) — the backend-supplied `public_key` is only trusted when it equals
 * the pin, so a compromised backend cannot swap in its own key. When the pin is empty (dev builds)
 * we skip signature verification but STILL enforce the sha256 of the downloaded file, so a corrupted
 * or truncated download is never installed.
 *
 * Mirrors [CommandPoller]'s structure: a single cancellable coroutine loop owned by the caller's
 * scope.
 */
class OtaUpdater(
    private val context: Context,
    private val client: DeviceKitClient,
    private val scope: CoroutineScope,
) {
    companion object {
        private const val TAG = "OtaUpdater"
        private const val CHECK_INTERVAL_MS = 15 * 60 * 1000L // ~15 minutes
    }

    private var job: Job? = null

    fun start(deviceIdProvider: () -> String?) {
        job?.cancel()
        job = scope.launch {
            while (isActive) {
                val deviceId = deviceIdProvider()
                if (deviceId != null) {
                    try {
                        checkOnce(deviceId)
                    } catch (e: Exception) {
                        // The loop must survive any single failure — never let an update attempt
                        // crash the polling coroutine.
                        LogBuffer.log(TAG, "update check error: ${e.message}", LogBuffer.Level.ERROR)
                    }
                }
                delay(CHECK_INTERVAL_MS)
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
    }

    private fun checkOnce(deviceId: String) {
        val response = client.checkUpdate(deviceId) ?: return
        if (!response.optBoolean("update", false)) return

        val manifest = response.optJSONObject("manifest") ?: run {
            LogBuffer.log(TAG, "update offered without manifest", LogBuffer.Level.ERROR)
            return
        }
        val rolloutId = response.optString("rollout_id")
        val releaseId = manifest.optString("release_id")
        val versionCode = manifest.optInt("version_code")
        val expectedSha = manifest.optString("sha256").lowercase()
        val downloadPath = response.optString("download_path")
        val signatureHex = response.optString("signature")
        val offeredPubKey = response.optString("public_key")

        if (releaseId.isEmpty() || downloadPath.isEmpty()) {
            LogBuffer.log(TAG, "update offer missing release_id/download_path", LogBuffer.Level.ERROR)
            return
        }

        LogBuffer.log(TAG, "update offered: release=$releaseId version_code=$versionCode")

        // --- a. Verify the Ed25519 signature over the canonical manifest --------------------
        val pinnedKey = BuildConfig.OTA_PUBLIC_KEY
        if (pinnedKey.isNotEmpty()) {
            if (offeredPubKey != pinnedKey) {
                LogBuffer.log(TAG, "pinned pubkey mismatch — refusing update", LogBuffer.Level.ERROR)
                client.reportUpdateStatus(deviceId, rolloutId, "failed", null, "pubkey mismatch")
                return
            }
            val canonical = canonicalManifestBytes(manifest)
            val verified = try {
                verifyEd25519(pinnedKey, canonical, signatureHex)
            } catch (e: Exception) {
                LogBuffer.log(TAG, "signature verify threw: ${e.message}", LogBuffer.Level.ERROR)
                false
            }
            if (!verified) {
                LogBuffer.log(TAG, "signature verification failed — refusing update", LogBuffer.Level.ERROR)
                client.reportUpdateStatus(deviceId, rolloutId, "failed", null, "signature invalid")
                return
            }
            LogBuffer.log(TAG, "signature verified against pinned key")
        } else {
            // Dev build with no pin: cannot authenticate the publisher, but the sha256 check below
            // still guards download integrity.
            LogBuffer.log(TAG, "OTA_PUBLIC_KEY not pinned — skipping signature verify (dev)", LogBuffer.Level.ERROR)
        }

        // --- b. Download the APK ------------------------------------------------------------
        val otaDir = File(context.filesDir, "ota")
        val apkFile = File(otaDir, "$releaseId.apk")
        client.reportUpdateStatus(deviceId, rolloutId, "downloading", null, null)
        LogBuffer.log(TAG, "downloading APK to ${apkFile.absolutePath}")
        val downloaded = try {
            client.downloadApk(downloadPath, apkFile)
        } catch (e: Exception) {
            LogBuffer.log(TAG, "download threw: ${e.message}", LogBuffer.Level.ERROR)
            false
        }
        if (!downloaded) {
            LogBuffer.log(TAG, "download failed", LogBuffer.Level.ERROR)
            client.reportUpdateStatus(deviceId, rolloutId, "failed", null, "download failed")
            apkFile.delete()
            return
        }

        // --- c. Verify the downloaded file's sha256 ----------------------------------------
        val actualSha = try {
            sha256Hex(apkFile)
        } catch (e: Exception) {
            LogBuffer.log(TAG, "sha256 compute threw: ${e.message}", LogBuffer.Level.ERROR)
            ""
        }
        if (actualSha != expectedSha) {
            LogBuffer.log(TAG, "sha256 mismatch: expected=$expectedSha actual=$actualSha", LogBuffer.Level.ERROR)
            client.reportUpdateStatus(deviceId, rolloutId, "failed", null, "sha256 mismatch")
            apkFile.delete()
            return
        }
        LogBuffer.log(TAG, "sha256 verified")

        // --- d. Install --------------------------------------------------------------------
        client.reportUpdateStatus(deviceId, rolloutId, "installing", null, null)
        LogBuffer.log(TAG, "installing via pm install")
        // NOTE: `pm install -r` self-update only succeeds when the agent process has shell/
        // device-owner privileges (e.g. launched via adb, or the app is a device owner). For an
        // unprivileged production build the correct path is a PackageInstaller session with a
        // user-confirmation intent (or a silent session when device-owner). That is a documented
        // TODO — deliberately not implemented here to keep this phase to the signed-download flow.
        val result = try {
            execShell("pm install -r \"${apkFile.absolutePath}\"")
        } catch (e: Exception) {
            LogBuffer.log(TAG, "install threw: ${e.message}", LogBuffer.Level.ERROR)
            client.reportUpdateStatus(deviceId, rolloutId, "failed", null, e.message ?: "install failed")
            apkFile.delete()
            return
        }

        if (result.exitCode == 0) {
            LogBuffer.log(TAG, "install succeeded (version_code=$versionCode)")
            client.reportUpdateStatus(deviceId, rolloutId, "installed", versionCode, null)
        } else {
            LogBuffer.log(TAG, "install failed: ${result.output}", LogBuffer.Level.ERROR)
            client.reportUpdateStatus(deviceId, rolloutId, "failed", null, result.output)
        }
        // On success the system replaces the running package; the installed APK is no longer needed.
        apkFile.delete()
    }

    /**
     * Build the canonical bytes the backend signed: compact JSON of exactly the 5 manifest fields,
     * keys sorted ascending, no whitespace — matching Python's
     * `json.dumps(manifest, sort_keys=True, separators=(",",":"))`.
     *
     * Field types are fixed by the contract: release_id/version_name/sha256 are strings (quoted),
     * version_code/size_bytes are integers (bare). Emitting them explicitly keeps the serialization
     * deterministic and independent of JSONObject's iteration order.
     */
    fun canonicalManifestBytes(manifest: JSONObject): ByteArray {
        // Sorted key order: release_id, sha256, size_bytes, version_code, version_name
        val sb = StringBuilder()
        sb.append('{')
        sb.append("\"release_id\":").append(jsonString(manifest.optString("release_id")))
        sb.append(',')
        sb.append("\"sha256\":").append(jsonString(manifest.optString("sha256")))
        sb.append(',')
        sb.append("\"size_bytes\":").append(manifest.optLong("size_bytes"))
        sb.append(',')
        sb.append("\"version_code\":").append(manifest.optLong("version_code"))
        sb.append(',')
        sb.append("\"version_name\":").append(jsonString(manifest.optString("version_name")))
        sb.append('}')
        return sb.toString().toByteArray(Charsets.UTF_8)
    }

    /** Minimal JSON string escaping matching what `json.dumps` emits for these fields. */
    private fun jsonString(value: String): String {
        val sb = StringBuilder(value.length + 2)
        sb.append('"')
        for (c in value) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                '\b' -> sb.append("\\b")
                '\u000C' -> sb.append("\\f")
                else -> if (c < ' ') {
                    sb.append("\\u").append(String.format("%04x", c.code))
                } else {
                    sb.append(c)
                }
            }
        }
        sb.append('"')
        return sb.toString()
    }

    private fun verifyEd25519(publicKeyHex: String, message: ByteArray, signatureHex: String): Boolean {
        if (signatureHex.isEmpty()) return false
        val pubKeyBytes = hexToBytes(publicKeyHex)
        val sigBytes = hexToBytes(signatureHex)
        val params = Ed25519PublicKeyParameters(pubKeyBytes, 0)
        val signer = Ed25519Signer()
        signer.init(false, params)
        signer.update(message, 0, message.size)
        return signer.verifySignature(sigBytes)
    }

    private fun sha256Hex(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(8192)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return bytesToHex(digest.digest())
    }

    private fun hexToBytes(hex: String): ByteArray {
        val clean = hex.trim()
        require(clean.length % 2 == 0) { "odd-length hex string" }
        val out = ByteArray(clean.length / 2)
        var i = 0
        while (i < clean.length) {
            out[i / 2] = ((Character.digit(clean[i], 16) shl 4) + Character.digit(clean[i + 1], 16)).toByte()
            i += 2
        }
        return out
    }

    private fun bytesToHex(bytes: ByteArray): String {
        val sb = StringBuilder(bytes.size * 2)
        for (b in bytes) {
            sb.append(String.format("%02x", b.toInt() and 0xff))
        }
        return sb.toString()
    }
}
