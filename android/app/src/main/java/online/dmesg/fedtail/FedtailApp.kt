package online.dmesg.fedtail

import android.app.Application
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.Date

/** Python is started once per process, before any screen asks the core for anything. */
class FedtailApp : Application() {
    override fun onCreate() {
        super.onCreate()
        keepCrashes()
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        DeviceTranslator.context = applicationContext
        SafTree.context = applicationContext  // sync through a folder the picker gave
        Notifier.channel(this)
        Notifier.schedule(this)
    }

    /** An exception nobody caught closes the app: its trace goes to a file first; the next
     *  start puts it into the logs (bridge.py's CRASH_FILE) and offers the report. */
    private fun keepCrashes() {
        val system = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, e ->
            try {
                File(filesDir, CRASH_FILE).appendText("${Date()} ${BuildConfig.VERSION_NAME}" +
                    " (${thread.name})\n${Log.getStackTraceString(e)}\n")
            } catch (_: Throwable) {}
            system?.uncaughtException(thread, e)
        }
    }

    companion object {
        const val CRASH_FILE = "crash.txt"
    }
}
