package com.devicekit.agent.server

import android.content.Context
import android.content.pm.PackageManager
import com.devicekit.agent.DeviceState
import com.devicekit.agent.server.routes.execShell
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.file.FileSystems

/**
 * The agent trust boundary (plan 25 part 1): a FIXED allowlist of read-only survey
 * primitives the backend may ask this device to run.
 *
 * The backend never sends shell text over the command-poll channel — it sends a primitive
 * NAME plus typed args, and this object picks a hard-coded, read-only implementation. Any
 * command that is not `survey.<allowlisted-primitive>` is refused. No primitive ever returns
 * whole-file contents: env/secret files can be probed for existence/metadata but never read.
 *
 * This mirrors the server-side allowlist in `backend/devicekit/agent_primitives.py`; keeping
 * the two in sync is the contract. The device is the last line of enforcement — even if the
 * server were compromised, it cannot make the agent run an off-list command here.
 */
object SurveyPrimitives {

    const val COMMAND_PREFIX = "survey."
    const val BATCH_COMMAND = "survey.batch"

    /** Every primitive the device will execute. Anything else is refused. */
    val ALLOWED: Set<String> = setOf(
        "file.exists", "file.stat", "fs.glob",
        "app.status", "app.list", "process.list", "metrics.snapshot"
    )

    fun isSurveyCommand(command: String): Boolean = command.startsWith(COMMAND_PREFIX)

    /**
     * Run a whole probe in one call (the `batch_survey` capability). [args] is
     * `{primitives: [{primitive, args}, ...]}`; the reply is `{results: [{primitive, result}
     * | {primitive, error}]}`. Each step is still validated against the allowlist, so batching
     * never widens what the device will run.
     */
    fun executeBatch(context: Context, args: JSONObject): JSONObject {
        val requested = args.optJSONArray("primitives") ?: JSONArray()
        val results = JSONArray()
        for (i in 0 until requested.length()) {
            val step = requested.optJSONObject(i) ?: continue
            val primitive = step.optString("primitive")
            val stepArgs = step.optJSONObject("args") ?: JSONObject()
            val entry = JSONObject().put("primitive", primitive)
            try {
                entry.put("result", execute(context, COMMAND_PREFIX + primitive, stepArgs))
            } catch (e: Exception) {
                entry.put("error", e.message ?: "primitive failed")
            }
            results.put(entry)
        }
        return JSONObject().put("results", results)
    }

    /**
     * Execute an allowlisted primitive. [command] is the full `survey.<name>` string from the
     * poll channel. Throws [SecurityException] if the primitive is off the allowlist — the
     * caller turns that into an error result, never a shell fallback.
     */
    fun execute(context: Context, command: String, args: JSONObject): JSONObject {
        val name = command.removePrefix(COMMAND_PREFIX)
        if (name !in ALLOWED) {
            throw SecurityException("primitive '$name' is not on the read-only allowlist")
        }
        return when (name) {
            "file.exists" -> fileExists(args)
            "file.stat" -> fileStat(args)
            "fs.glob" -> fsGlob(args)
            "app.status" -> appStatus(context, args)
            "app.list" -> appList(context, args)
            "process.list" -> processList()
            "metrics.snapshot" -> metricsSnapshot()
            else -> throw SecurityException("primitive '$name' is not on the read-only allowlist")
        }
    }

    // --- primitives (all read-only; none returns file contents) ---------------------------

    private fun fileExists(args: JSONObject): JSONObject {
        val path = args.getString("path")
        return JSONObject().put("path", path).put("exists", File(path).exists())
    }

    private fun fileStat(args: JSONObject): JSONObject {
        val path = args.getString("path")
        val f = File(path)
        val out = JSONObject().put("path", path).put("exists", f.exists())
        if (f.exists()) {
            out.put("size", f.length())
            out.put("mtime", f.lastModified() / 1000.0)
            out.put("is_dir", f.isDirectory)
            // Permission bits, never contents — this is "listed by path only".
            val mode = (if (f.canRead()) "r" else "-") +
                    (if (f.canWrite()) "w" else "-") +
                    (if (f.canExecute()) "x" else "-")
            out.put("mode", mode)
        }
        return out
    }

    private fun fsGlob(args: JSONObject): JSONObject {
        val pattern = args.getString("pattern")
        val limit = if (args.has("limit")) args.getInt("limit") else 500
        val matches = JSONArray()
        try {
            // Anchor the walk at the deepest literal directory prefix so we don't scan "/".
            val firstGlob = pattern.indexOfFirst { it == '*' || it == '?' || it == '[' }
            val base = if (firstGlob < 0) File(pattern).parent ?: "/"
            else pattern.substring(0, firstGlob).substringBeforeLast('/', "/")
            val matcher = FileSystems.getDefault().getPathMatcher("glob:$pattern")
            val root = File(base.ifEmpty { "/" })
            root.walkTopDown().maxDepth(8).forEach { f ->
                if (matches.length() >= limit) return@forEach
                if (matcher.matches(f.toPath())) matches.put(f.absolutePath)
            }
        } catch (e: Exception) {
            // A bad pattern yields no matches, never contents.
        }
        return JSONObject().put("pattern", pattern).put("matches", matches)
            .put("truncated", matches.length() >= limit)
    }

    private fun appStatus(context: Context, args: JSONObject): JSONObject {
        val pkg = args.getString("package")
        val out = JSONObject().put("package", pkg)
        try {
            val info = context.packageManager.getPackageInfo(pkg, 0)
            out.put("installed", true)
            out.put("version", info.versionName)
        } catch (e: PackageManager.NameNotFoundException) {
            out.put("installed", false)
            out.put("version", JSONObject.NULL)
        }
        // Running check via pidof (read-only).
        val res = execShell("pidof $pkg")
        out.put("running", res.exitCode == 0 && res.output.isNotBlank())
        return out
    }

    private fun appList(context: Context, args: JSONObject): JSONObject {
        val includeSystem = args.optBoolean("include_system", false)
        val packages = JSONArray()
        val flags = 0
        for (info in context.packageManager.getInstalledPackages(flags)) {
            val appInfo = info.applicationInfo ?: continue
            val isSystem = (appInfo.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0
            if (isSystem && !includeSystem) continue
            packages.put(JSONObject()
                .put("package", info.packageName)
                .put("version", info.versionName ?: JSONObject.NULL))
        }
        return JSONObject().put("packages", packages).put("count", packages.length())
    }

    private fun processList(): JSONObject {
        val processes = JSONArray()
        val res = execShell("ps -A -o PID,NAME")
        if (res.exitCode == 0) {
            res.output.lineSequence().drop(1).forEach { line ->
                val parts = line.trim().split(Regex("\\s+"), limit = 2)
                if (parts.size == 2) {
                    processes.put(JSONObject()
                        .put("pid", parts[0].toIntOrNull() ?: -1)
                        .put("name", parts[1]))
                }
            }
        }
        return JSONObject().put("processes", processes).put("count", processes.length())
    }

    private fun metricsSnapshot(): JSONObject {
        // Reuse the metrics DeviceState already collects — no new polling, no contents.
        val state = DeviceState.toJson()
        return state.optJSONObject("metrics") ?: JSONObject()
    }
}
