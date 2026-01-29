package com.devicekit.agent

/**
 * Singleton log buffer for in-app log viewing.
 * Thread-safe, capped at 500 entries, supports listener pattern.
 */
object LogBuffer {

    enum class Level { EVENT, ERROR, METRICS }

    data class LogEntry(
        val timestamp: Long = System.currentTimeMillis(),
        val source: String,
        val message: String,
        val level: Level = Level.EVENT
    )

    private const val MAX_ENTRIES = 500
    private val _entries = ArrayDeque<LogEntry>(MAX_ENTRIES)
    private val _listeners = mutableListOf<(LogEntry) -> Unit>()

    val entries: List<LogEntry>
        get() = synchronized(_entries) { _entries.toList() }

    fun log(source: String, message: String, level: Level = Level.EVENT) {
        val entry = LogEntry(
            source = source,
            message = message,
            level = level
        )
        synchronized(_entries) {
            if (_entries.size >= MAX_ENTRIES) {
                _entries.removeFirst()
            }
            _entries.addLast(entry)
        }
        notifyListeners(entry)
    }

    fun clear() {
        synchronized(_entries) {
            _entries.clear()
        }
    }

    fun addListener(listener: (LogEntry) -> Unit) {
        synchronized(_listeners) {
            _listeners.add(listener)
        }
    }

    fun removeListener(listener: (LogEntry) -> Unit) {
        synchronized(_listeners) {
            _listeners.remove(listener)
        }
    }

    private fun notifyListeners(entry: LogEntry) {
        synchronized(_listeners) {
            _listeners.forEach { it(entry) }
        }
    }
}
