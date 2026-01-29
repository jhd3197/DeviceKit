package com.devicekit.agent.server.routes

import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject

class AppRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        return when {
            method == NanoHTTPD.Method.GET && uri == "/app/list" -> handleList(session)
            method == NanoHTTPD.Method.GET && uri == "/app/info" -> handleInfo(session)
            method == NanoHTTPD.Method.GET && uri == "/app/current" -> handleCurrent()
            method == NanoHTTPD.Method.GET && uri == "/app/search" -> handleSearch(session)
            method == NanoHTTPD.Method.POST && uri == "/app/launch" -> handleLaunch(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/app/stop" -> handleStop(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/app/install" -> handleInstall(session, bodyParams)
            method == NanoHTTPD.Method.POST && uri == "/app/uninstall" -> handleUninstall(session, bodyParams)
            else -> null
        }
    }

    private fun handleList(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val filter = session.parms["filter"] ?: "all"
        val pm = context.packageManager
        val packages = pm.getInstalledPackages(0)

        val apps = JSONArray()
        for (pkg in packages) {
            val isSystem = (pkg.applicationInfo?.flags ?: 0) and ApplicationInfo.FLAG_SYSTEM != 0
            when (filter) {
                "user" -> if (isSystem) continue
                "system" -> if (!isSystem) continue
            }
            apps.put(packageToJson(pm, pkg))
        }
        return jsonResponse(json = JSONObject().apply {
            put("apps", apps)
            put("count", apps.length())
        })
    }

    private fun handleInfo(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val packageName = session.parms["package"]
            ?: return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "package required")
        return try {
            val pm = context.packageManager
            val pkg = pm.getPackageInfo(packageName, PackageManager.GET_PERMISSIONS or PackageManager.GET_ACTIVITIES)
            val appInfo = pkg.applicationInfo

            val activities = JSONArray()
            pkg.activities?.forEach { act ->
                activities.put(act.name)
            }

            val permissions = JSONArray()
            pkg.requestedPermissions?.forEach { perm ->
                permissions.put(perm)
            }

            val sourceDir = appInfo?.sourceDir
            val apkSize = if (sourceDir != null) java.io.File(sourceDir).length() else 0

            jsonResponse(json = JSONObject().apply {
                put("package", packageName)
                put("label", appInfo?.let { pm.getApplicationLabel(it).toString() } ?: packageName)
                put("version_name", pkg.versionName)
                put("version_code", pkg.longVersionCode)
                put("is_system", (appInfo?.flags ?: 0) and ApplicationInfo.FLAG_SYSTEM != 0)
                put("enabled", appInfo?.enabled ?: false)
                put("target_sdk", appInfo?.targetSdkVersion ?: 0)
                put("min_sdk", appInfo?.minSdkVersion ?: 0)
                put("apk_size", apkSize)
                put("source_dir", sourceDir)
                put("activities", activities)
                put("permissions", permissions)
                put("first_install", pkg.firstInstallTime)
                put("last_update", pkg.lastUpdateTime)
            })
        } catch (e: PackageManager.NameNotFoundException) {
            errorResponse(NanoHTTPD.Response.Status.NOT_FOUND, "Package not found: $packageName")
        }
    }

    private fun handleCurrent(): NanoHTTPD.Response {
        val result = execShell("dumpsys activity activities | grep mResumedActivity")
        val output = result.output
        // Parse: mResumedActivity: ActivityRecord{... com.package/.Activity ...}
        val regex = Regex("""(\S+)/(\S+)""")
        val match = regex.find(output)
        return jsonResponse(json = JSONObject().apply {
            put("package", match?.groupValues?.get(1) ?: com.devicekit.agent.DeviceState.currentPackage)
            put("activity", match?.groupValues?.get(2) ?: com.devicekit.agent.DeviceState.currentActivity)
        })
    }

    private fun handleSearch(session: NanoHTTPD.IHTTPSession): NanoHTTPD.Response {
        val query = session.parms["q"]?.lowercase()
            ?: return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "q required")
        val pm = context.packageManager
        val packages = pm.getInstalledPackages(0)
        val results = JSONArray()
        for (pkg in packages) {
            val label = pkg.applicationInfo?.let { pm.getApplicationLabel(it).toString() } ?: ""
            val pkgName = pkg.packageName ?: ""
            if (label.lowercase().contains(query) || pkgName.lowercase().contains(query)) {
                results.put(packageToJson(pm, pkg))
            }
        }
        return jsonResponse(json = JSONObject().apply {
            put("query", query)
            put("results", results)
            put("count", results.length())
        })
    }

    private fun handleLaunch(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val packageName = body.optString("package", "")
        if (packageName.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "package required")
        }
        return try {
            val intent = context.packageManager.getLaunchIntentForPackage(packageName)
            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(intent)
                jsonResponse(json = JSONObject().apply {
                    put("success", true)
                    put("package", packageName)
                })
            } else {
                // Fallback: use am start
                val result = execShell("am start -n $(cmd package resolve-activity --brief $packageName | tail -n 1)")
                jsonResponse(json = JSONObject().apply {
                    put("success", result.exitCode == 0)
                    put("package", packageName)
                    put("output", result.output)
                })
            }
        } catch (e: Exception) {
            errorResponse(message = "Launch failed: ${e.message}")
        }
    }

    private fun handleStop(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val packageName = body.optString("package", "")
        if (packageName.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "package required")
        }
        val result = execShell("am force-stop $packageName")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("package", packageName)
        })
    }

    private fun handleInstall(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val path = body.optString("path", "")
        if (path.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "path required")
        }
        val result = execShell("pm install -r \"$path\"")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.output.contains("Success"))
            put("output", result.output)
            put("path", path)
        })
    }

    private fun handleUninstall(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val packageName = body.optString("package", "")
        if (packageName.isEmpty()) {
            return errorResponse(NanoHTTPD.Response.Status.BAD_REQUEST, "package required")
        }
        val result = execShell("pm uninstall $packageName")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.output.contains("Success"))
            put("output", result.output)
            put("package", packageName)
        })
    }

    private fun packageToJson(pm: PackageManager, pkg: PackageInfo): JSONObject {
        val appInfo = pkg.applicationInfo
        return JSONObject().apply {
            put("package", pkg.packageName)
            put("label", appInfo?.let { pm.getApplicationLabel(it).toString() } ?: pkg.packageName)
            put("version_name", pkg.versionName)
            put("version_code", pkg.longVersionCode)
            put("is_system", (appInfo?.flags ?: 0) and ApplicationInfo.FLAG_SYSTEM != 0)
            put("enabled", appInfo?.enabled ?: false)
        }
    }
}
