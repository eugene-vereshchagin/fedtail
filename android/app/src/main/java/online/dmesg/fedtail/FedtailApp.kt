package online.dmesg.fedtail

import android.app.Application
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/** Python is started once per process, before any screen asks the core for anything. */
class FedtailApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
    }
}
