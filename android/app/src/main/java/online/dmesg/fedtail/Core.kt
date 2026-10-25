package online.dmesg.fedtail

import android.content.Context
import com.chaquo.python.Python
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * The Kotlin face of fedtail's core: every call goes to fedtail_android/bridge.py, takes
 * and gives plain values (JSON), and runs off the main thread — Python and the network
 * never block a frame. A call that failed answers {"error": "…"}: see [failed].
 */
object Core {
    private val bridge by lazy { Python.getInstance().getModule("fedtail_android.bridge") }

    private suspend fun call(name: String, vararg args: Any?): String =
        withContext(Dispatchers.IO) { bridge.callAttr(name, *args).toString() }

    private suspend fun obj(name: String, vararg args: Any?) = JSONObject(call(name, *args))

    fun failed(o: JSONObject): String? = if (o.has("error")) o.optString("error") else null

    suspend fun start(context: Context, lang: String, demo: Boolean): JSONObject = obj(
        "start", context.filesDir.absolutePath, context.cacheDir.absolutePath, lang, demo, true)

    suspend fun selfcheckSteps(): JSONArray = JSONArray(call("selfcheck_steps"))
    suspend fun selfcheckStep(name: String) = obj("selfcheck_step", name)
    suspend fun selfcheckReport(results: JSONArray, device: JSONObject) =
        obj("selfcheck_report", results.toString(), device.toString())

    suspend fun state() = obj("state")
    suspend fun loginBegin(server: String) = obj("login_begin", server)
    suspend fun loginFinish(code: String) = obj("login_finish", code)
    suspend fun open() = obj("open")
    suspend fun lanes() = JSONArray(call("lanes"))
    suspend fun lane(name: String, keep: Boolean) = obj("lane", name, keep)
    suspend fun hub() = obj("hub")
    suspend fun older(name: String) = obj("older", name)
    suspend fun placeAct(act: List<String>, confirmed: Boolean) =
        obj("place_act", JSONArray(act).toString(), confirmed)
    suspend fun pin(names: List<String>) = obj("pin", JSONArray(names).toString())
    suspend fun commandPreview(line: String) = obj("command_preview", line)
    suspend fun command(line: String, confirmed: Boolean) = obj("command", line, confirmed)
    suspend fun read(ids: List<String>) = obj("read", JSONArray(ids).toString())
    suspend fun refresh() = obj("refresh")
    suspend fun pause(on: Boolean) = obj("pause", on)
    suspend fun thread(id: String) = obj("thread", id)
    suspend fun post(body: JSONObject) = obj("post", body.toString())
    suspend fun act(action: String, id: String) = obj("act", action, id)
    suspend fun menu(id: String) = obj("menu", id)
    suspend fun threadAct(action: String, id: String) = obj("thread_act", action, id)
    suspend fun resolve(url: String) = obj("resolve", url)
    suspend fun settings() = obj("settings")
    suspend fun settingSet(section: String, key: String, json: String) =
        obj("setting_set", section, key, json)
    suspend fun settingsApply() = obj("settings_apply")
    suspend fun configText() = obj("config_text")
    suspend fun configSave(text: String) = obj("config_save", text)
    suspend fun syncStatus() = obj("sync_status")
    suspend fun syncLoginBegin() = obj("sync_login_begin")
    suspend fun syncLoginFinish(code: String) = obj("sync_login_finish", code)
    suspend fun syncKey() = obj("sync_key")
    suspend fun syncJoin(text: String) = obj("sync_join", text)
    suspend fun syncNow() = obj("sync_now")

    /** Blocks up to [seconds] for a change in the lanes; → the version now. */
    suspend fun waitChange(since: Int, seconds: Int): Int =
        withContext(Dispatchers.IO) { bridge.callAttr("wait", since, seconds).toInt() }
}
