package com.faro.protocol

/**
 * Raw JNI surface of libfaro_agent_jni.so — the Faro agent daemon compiled
 * from the Faro repo's Rust crates. Every call except [nativeInit] returns a
 * HostStatus-shaped JSON string (or {"error": "..."}); parsing lives in
 * [FaroAgentController]. Do not call these directly from UI code.
 */
internal object FaroNative {
    init {
        System.loadLibrary("faro_agent_jni")
    }

    external fun nativeInit(configDir: String, deviceName: String)
    external fun nativeSetEnabled(enabled: Boolean, port: Int): String
    external fun nativeStatus(): String
    external fun nativeOpenPairing(): String
    external fun nativeClosePairing(): String
    external fun nativeSetPolicy(allowExec: Boolean, allowWrite: Boolean): String
    external fun nativeRevokePeer(publicKey: String): String
    external fun nativeSetDeviceName(deviceName: String): String
}
