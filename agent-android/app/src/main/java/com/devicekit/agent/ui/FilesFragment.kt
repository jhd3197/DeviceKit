package com.devicekit.agent.ui

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.StatFs
import android.provider.Settings
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.devicekit.agent.R
import kotlinx.coroutines.*
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class FilesFragment : Fragment() {

    private lateinit var pathBar: View
    private lateinit var currentPathView: TextView
    private lateinit var btnUp: TextView
    private lateinit var btnHome: TextView
    private lateinit var storageBarView: View
    private lateinit var storageInfo: TextView
    private lateinit var itemCount: TextView
    private lateinit var loadingBar: ProgressBar
    private lateinit var emptyState: TextView
    private lateinit var fileList: RecyclerView
    private lateinit var storagePicker: View
    private lateinit var cardInternalStorage: View
    private lateinit var cardSdCard: View
    private lateinit var internalStorageInfo: TextView
    private lateinit var sdCardInfo: TextView
    private lateinit var permissionPrompt: View
    private lateinit var btnGrantPermission: View

    private var currentPath: String? = null // null = at storage picker root
    private var internalStorageRoot: String = Environment.getExternalStorageDirectory().absolutePath
    private var sdCardRoot: String? = null

    private val adapter = FileAdapter { entry -> onItemClick(entry) }
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    private lateinit var backCallback: OnBackPressedCallback

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_files, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        pathBar = view.findViewById(R.id.pathBar)
        currentPathView = view.findViewById(R.id.currentPath)
        btnUp = view.findViewById(R.id.btnUp)
        btnHome = view.findViewById(R.id.btnHome)
        storageBarView = view.findViewById(R.id.storageBar)
        storageInfo = view.findViewById(R.id.storageInfo)
        itemCount = view.findViewById(R.id.itemCount)
        loadingBar = view.findViewById(R.id.loadingBar)
        emptyState = view.findViewById(R.id.emptyState)
        fileList = view.findViewById(R.id.fileList)
        storagePicker = view.findViewById(R.id.storagePicker)
        cardInternalStorage = view.findViewById(R.id.cardInternalStorage)
        cardSdCard = view.findViewById(R.id.cardSdCard)
        internalStorageInfo = view.findViewById(R.id.internalStorageInfo)
        sdCardInfo = view.findViewById(R.id.sdCardInfo)
        permissionPrompt = view.findViewById(R.id.permissionPrompt)
        btnGrantPermission = view.findViewById(R.id.btnGrantPermission)

        fileList.layoutManager = LinearLayoutManager(requireContext())
        fileList.adapter = adapter

        btnUp.setOnClickListener { navigateUp() }
        btnHome.setOnClickListener { showStoragePicker() }

        cardInternalStorage.setOnClickListener {
            currentPath = internalStorageRoot
            loadDirectory()
        }

        cardSdCard.setOnClickListener {
            sdCardRoot?.let { root ->
                currentPath = root
                loadDirectory()
            }
        }

        btnGrantPermission.setOnClickListener {
            requestStoragePermission()
        }

        // Detect SD card
        detectSdCard()

        // Setup back navigation
        backCallback = object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (currentPath != null) {
                    navigateUp()
                } else {
                    // At storage picker root — let system handle (e.g. close app)
                    isEnabled = false
                    requireActivity().onBackPressedDispatcher.onBackPressed()
                    isEnabled = true
                }
            }
        }
        requireActivity().onBackPressedDispatcher.addCallback(viewLifecycleOwner, backCallback)

        // Check permissions and show appropriate view
        checkAndShow()
    }

    override fun onResume() {
        super.onResume()
        // Re-check permission on resume (user may have just granted it)
        checkAndShow()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        scope.cancel()
    }

    private fun checkAndShow() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && !Environment.isExternalStorageManager()) {
            showPermissionPrompt()
        } else if (currentPath == null) {
            showStoragePicker()
        } else {
            loadDirectory()
        }
    }

    private fun showPermissionPrompt() {
        permissionPrompt.visibility = View.VISIBLE
        storagePicker.visibility = View.GONE
        pathBar.visibility = View.GONE
        storageBarView.visibility = View.GONE
        fileList.visibility = View.GONE
        emptyState.visibility = View.GONE
        loadingBar.visibility = View.GONE
    }

    private fun requestStoragePermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                    data = Uri.parse("package:${requireContext().packageName}")
                }
                startActivity(intent)
            } catch (_: Exception) {
                val intent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
                startActivity(intent)
            }
        }
    }

    private fun showStoragePicker() {
        currentPath = null
        permissionPrompt.visibility = View.GONE
        storagePicker.visibility = View.VISIBLE
        pathBar.visibility = View.GONE
        storageBarView.visibility = View.GONE
        fileList.visibility = View.GONE
        emptyState.visibility = View.GONE
        loadingBar.visibility = View.GONE
        adapter.submitList(emptyList())

        updateStoragePickerInfo()
    }

    private fun updateStoragePickerInfo() {
        try {
            val stat = StatFs(internalStorageRoot)
            val total = stat.totalBytes
            val free = stat.freeBytes
            val used = total - free
            internalStorageInfo.text = "${formatSize(used)} used / ${formatSize(total)} total"
        } catch (_: Exception) {
            internalStorageInfo.text = ""
        }

        sdCardRoot?.let { root ->
            try {
                val stat = StatFs(root)
                val total = stat.totalBytes
                val free = stat.freeBytes
                val used = total - free
                sdCardInfo.text = "${formatSize(used)} used / ${formatSize(total)} total"
            } catch (_: Exception) {
                sdCardInfo.text = ""
            }
        }
    }

    private fun detectSdCard() {
        val dirs = requireContext().getExternalFilesDirs(null)
        if (dirs.size > 1) {
            // Second entry is the SD card app-specific dir.
            // Walk up to the storage volume root (typically /storage/XXXX-XXXX)
            val sdAppDir = dirs[1] ?: return
            var path = sdAppDir
            while (path.parentFile != null) {
                if (path.parentFile?.absolutePath == "/storage") {
                    sdCardRoot = path.absolutePath
                    cardSdCard.visibility = View.VISIBLE
                    return
                }
                path = path.parentFile!!
            }
        }
    }

    private fun loadDirectory() {
        val path = currentPath ?: return

        permissionPrompt.visibility = View.GONE
        storagePicker.visibility = View.GONE
        pathBar.visibility = View.VISIBLE
        storageBarView.visibility = View.VISIBLE

        currentPathView.text = path
        loadingBar.visibility = View.VISIBLE
        emptyState.visibility = View.GONE

        updateStorageInfo(path)

        scope.launch {
            val entries = withContext(Dispatchers.IO) { listFiles(path) }
            if (!isAdded) return@launch

            loadingBar.visibility = View.GONE
            adapter.submitList(entries)
            itemCount.text = "${entries.size} items"

            if (entries.isEmpty()) {
                emptyState.visibility = View.VISIBLE
                fileList.visibility = View.GONE
            } else {
                emptyState.visibility = View.GONE
                fileList.visibility = View.VISIBLE
            }
        }
    }

    private fun listFiles(path: String): List<FileEntry> {
        val dir = File(path)
        if (!dir.exists() || !dir.canRead()) return emptyList()

        val files = dir.listFiles() ?: return emptyList()
        return files
            .sortedWith(compareByDescending<File> { it.isDirectory }.thenBy { it.name.lowercase() })
            .map { file ->
                FileEntry(
                    name = file.name,
                    path = file.absolutePath,
                    isDirectory = file.isDirectory,
                    size = if (file.isFile) file.length() else countChildren(file),
                    lastModified = file.lastModified(),
                    isHidden = file.isHidden
                )
            }
    }

    private fun countChildren(dir: File): Long {
        return try { (dir.listFiles()?.size ?: 0).toLong() } catch (_: Exception) { 0L }
    }

    private fun onItemClick(entry: FileEntry) {
        if (entry.isDirectory) {
            currentPath = entry.path
            loadDirectory()
            fileList.scrollToPosition(0)
        } else {
            Toast.makeText(requireContext(), entry.name, Toast.LENGTH_SHORT).show()
        }
    }

    private fun navigateUp() {
        val path = currentPath ?: return
        // If at a storage root, go back to picker
        if (path == internalStorageRoot || path == sdCardRoot) {
            showStoragePicker()
            return
        }
        val parent = File(path).parent
        if (parent != null) {
            currentPath = parent
            loadDirectory()
        } else {
            showStoragePicker()
        }
    }

    private fun updateStorageInfo(path: String) {
        try {
            val stat = StatFs(path)
            val totalBytes = stat.totalBytes
            val freeBytes = stat.freeBytes
            val usedBytes = totalBytes - freeBytes
            storageInfo.text = "${formatSize(usedBytes)} used / ${formatSize(totalBytes)} total"
        } catch (_: Exception) {
            storageInfo.text = ""
        }
    }

    companion object {
        fun formatSize(bytes: Long): String {
            return when {
                bytes >= 1_073_741_824 -> String.format("%.1f GB", bytes / 1_073_741_824.0)
                bytes >= 1_048_576 -> String.format("%.1f MB", bytes / 1_048_576.0)
                bytes >= 1_024 -> String.format("%.1f KB", bytes / 1_024.0)
                else -> "$bytes B"
            }
        }

        fun formatDate(timestamp: Long): String {
            if (timestamp == 0L) return ""
            return SimpleDateFormat("MMM d, yyyy HH:mm", Locale.getDefault()).format(Date(timestamp))
        }
    }

    // ---- Data classes ----

    data class FileEntry(
        val name: String,
        val path: String,
        val isDirectory: Boolean,
        val size: Long,
        val lastModified: Long,
        val isHidden: Boolean
    )

    // ---- Adapter ----

    class FileAdapter(private val onClick: (FileEntry) -> Unit) :
        RecyclerView.Adapter<FileAdapter.ViewHolder>() {

        private var items: List<FileEntry> = emptyList()

        fun submitList(newItems: List<FileEntry>) {
            items = newItems
            notifyDataSetChanged()
        }

        override fun getItemCount(): Int = items.size

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context).inflate(R.layout.item_file, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            holder.bind(items[position])
        }

        inner class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            private val icon: TextView = view.findViewById(R.id.fileIcon)
            private val name: TextView = view.findViewById(R.id.fileName)
            private val details: TextView = view.findViewById(R.id.fileDetails)
            private val chevron: TextView = view.findViewById(R.id.fileChevron)

            fun bind(entry: FileEntry) {
                name.text = entry.name
                icon.text = getIcon(entry)

                if (entry.isDirectory) {
                    val childCount = entry.size
                    details.text = if (childCount > 0) "$childCount items" else "Empty"
                    chevron.visibility = View.VISIBLE
                } else {
                    val sizeStr = formatSize(entry.size)
                    val dateStr = formatDate(entry.lastModified)
                    details.text = "$sizeStr  $dateStr"
                    chevron.visibility = View.GONE
                }

                // Dim hidden files
                val alpha = if (entry.isHidden) 0.5f else 1.0f
                name.alpha = alpha
                icon.alpha = alpha

                itemView.setOnClickListener { onClick(entry) }
            }

            private fun getIcon(entry: FileEntry): String {
                if (entry.isDirectory) return "\uD83D\uDCC1" // folder
                val ext = entry.name.substringAfterLast('.', "").lowercase()
                return when (ext) {
                    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg" -> "\uD83D\uDDBC"
                    "mp4", "mkv", "avi", "mov", "webm", "3gp" -> "\uD83C\uDFA5"
                    "mp3", "wav", "ogg", "flac", "aac", "m4a" -> "\uD83C\uDFB5"
                    "pdf" -> "\uD83D\uDCC4"
                    "zip", "tar", "gz", "rar", "7z" -> "\uD83D\uDCE6"
                    "apk" -> "\uD83D\uDCF1"
                    "txt", "log", "md", "csv" -> "\uD83D\uDCC3"
                    "json", "xml", "html", "css", "js", "kt", "java", "py" -> "\uD83D\uDCBB"
                    "db", "sqlite" -> "\uD83D\uDDC4"
                    else -> "\uD83D\uDCC4"
                }
            }
        }
    }
}
