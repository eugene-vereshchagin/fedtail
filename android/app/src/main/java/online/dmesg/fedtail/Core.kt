package online.dmesg.fedtail

import android.content.Context
import com.chaquo.python.Python
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * The Kotlin face of fedtail's core: every call goes to fedtail_android/bridge.py, takes
 * and gives plain values (JSON), and runs off the main thread — Python and the network
 * never block a frame.
 */
object Core {
    private val bridge by lazy { Python.getInstance().getModule("fedtail_android.bridge") }

    suspend fun start(context: Context): JSONObject = withContext(Dispatchers.IO) {
        val files = context.filesDir.absolutePath
        val cache = context.cacheDir.absolutePath
        JSONObject(bridge.callAttr("start", files, cache).toString())
    }

    suspend fun info(): JSONObject = withContext(Dispatchers.IO) {
        JSONObject(bridge.callAttr("info").toString())
    }
}
