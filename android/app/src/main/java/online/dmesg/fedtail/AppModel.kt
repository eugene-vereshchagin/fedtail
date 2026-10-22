package online.dmesg.fedtail

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

sealed interface Screen {
    data object Starting : Screen
    data class Failed(val text: String) : Screen
    data object Login : Screen
    data object Main : Screen
}

data class LaneItem(val name: String, val title: String, val unread: Int, val group: String?)

data class PostItem(
    val key: String, val id: String, val alias: String, val name: String,
    val handle: String, val created: String, val text: String, val warning: String,
    val unread: Boolean, val sharedBy: String, val contextHandle: String,
    val contextText: String, val replies: Int, val shares: Int, val likes: Int,
)

/** What the screens show and what they ask of the core; lives as long as the app's task. */
class AppModel(app: Application) : AndroidViewModel(app) {
    var screen by mutableStateOf<Screen>(Screen.Starting)
    var demo by mutableStateOf(false)
    var handle by mutableStateOf("")
    var newestFirst by mutableStateOf(false)
    var markOnScroll by mutableStateOf(true)

    var lanes by mutableStateOf(listOf<LaneItem>())
    var current by mutableStateOf<String?>(null)
    var title by mutableStateOf("")
    var posts by mutableStateOf(listOf<PostItem>())
    var divider by mutableStateOf<Pair<String, String>?>(null) // (post key, "new below · N")
    var opening by mutableStateOf(0) // grows each time a lane opens anew: the list re-aims
    var refreshing by mutableStateOf(false)
    var message by mutableStateOf<String?>(null)

    var loginServer by mutableStateOf("")
    var loginWaiting by mutableStateOf(false)
    var loginNeedsCode by mutableStateOf(false)
    var loginBusy by mutableStateOf(false)

    private var started = false
    private var version = -1
    private var watcher: Job? = null

    fun start(demo: Boolean) {
        if (started) return
        started = true
        this.demo = demo
        viewModelScope.launch {
            val lang = Locale.getDefault().language
            val info = Core.start(getApplication(), lang, demo)
            if (info.has("error")) {
                screen = Screen.Failed(info.optString("error") + "\n\n" + info.optString("trace"))
                return@launch
            }
            val st = Core.state()
            when {
                Core.failed(st) != null -> screen = Screen.Failed(Core.failed(st)!!)
                st.optBoolean("logged_in") -> openMain()
                else -> screen = Screen.Login
            }
        }
    }

    // ---- logging in --------------------------------------------------------------------
    fun beginLogin(openBrowser: (String) -> Unit) {
        if (loginBusy || loginServer.isBlank()) return
        loginBusy = true
        viewModelScope.launch {
            val got = Core.loginBegin(loginServer)
            loginBusy = false
            val err = Core.failed(got)
            if (err != null) {
                message = err
                return@launch
            }
            loginNeedsCode = !got.optBoolean("redirect")
            loginWaiting = true
            openBrowser(got.optString("url"))
        }
    }

    fun finishLogin(code: String) {
        if (code.isBlank() || loginBusy) return
        loginBusy = true
        viewModelScope.launch {
            val got = Core.loginFinish(code)
            loginBusy = false
            val err = Core.failed(got)
            if (err != null) {
                message = err
                return@launch
            }
            loginWaiting = false
            openMain()
        }
    }

    // ---- reading -----------------------------------------------------------------------
    private suspend fun openMain() {
        val got = Core.open()
        val err = Core.failed(got)
        if (err != null) {
            screen = Screen.Failed(err)
            return
        }
        val me = got.optJSONObject("me") ?: JSONObject()
        handle = me.optString("handle")
        newestFirst = me.optString("order") == "newest_first"
        markOnScroll = me.optString("mark_read", "on_scroll") == "on_scroll"
        lanes = parseLanes(got.optJSONArray("lanes") ?: JSONArray())
        val first = (0 until (got.optJSONArray("lanes")?.length() ?: 0))
            .map { got.getJSONArray("lanes").getJSONObject(it) }
            .firstOrNull { it.optBoolean("start") }?.optString("name")
            ?: lanes.firstOrNull { it.name == "home" }?.name ?: lanes.firstOrNull()?.name
        screen = Screen.Main
        first?.let { showLane(it) }
        watch()
    }

    fun showLane(name: String) {
        current = name
        viewModelScope.launch { loadLane(name, keep = false) }
    }

    private suspend fun loadLane(name: String, keep: Boolean) {
        val got = Core.lane(name, keep)
        val err = Core.failed(got)
        if (err != null) {
            message = err
            return
        }
        if (name != current) return // the reader moved on meanwhile
        title = got.optString("title")
        val arr = got.optJSONArray("posts") ?: JSONArray()
        var list = (0 until arr.length()).map { parsePost(arr.getJSONObject(it)) }
        if (newestFirst) list = list.reversed()
        posts = list
        val div = got.optJSONObject("divider")
        divider = div?.let { d ->
            list.firstOrNull { it.id == d.optString("before") }?.key?.let { it to d.optString("text") }
        }
        if (!keep) opening += 1
    }

    fun refresh() {
        refreshing = true
        viewModelScope.launch {
            Core.refresh()
            delay(8000) // the round's news reload the lane through watch(); then it stops
            refreshing = false
        }
    }

    fun markRead(keys: Collection<String>) {
        val ids = posts.filter { it.key in keys && it.unread }.map { it.id }
        if (ids.isEmpty()) return
        posts = posts.map { if (it.id in ids) it.copy(unread = false) else it }
        viewModelScope.launch { Core.read(ids) }
    }

    /** While on screen: whatever the core learns (a poll, sync) reloads what is shown. */
    private fun watch() {
        if (watcher?.isActive == true) return
        watcher = viewModelScope.launch {
            while (isActive) {
                val v = Core.waitChange(version, 25)
                if (v != version) {
                    version = v
                    lanes = parseLanes(Core.lanes())
                    current?.let { loadLane(it, keep = true) }
                    refreshing = false
                }
            }
        }
    }

    fun onForeground() {
        if (screen != Screen.Main) return
        viewModelScope.launch { Core.pause(false) }
        watch()
    }

    fun onBackground() {
        if (screen != Screen.Main) return
        watcher?.cancel()
        viewModelScope.launch { Core.pause(true) }
    }

    // ---- JSON → items ------------------------------------------------------------------
    private fun parseLanes(arr: JSONArray) = (0 until arr.length()).map {
        val o = arr.getJSONObject(it)
        LaneItem(o.optString("name"), o.optString("title"), o.optInt("unread"),
            if (o.isNull("group")) null else o.optString("group"))
    }

    private fun parsePost(o: JSONObject): PostItem {
        val acc = o.optJSONObject("account") ?: JSONObject()
        val ctx = o.optJSONObject("context")
        val counts = o.optJSONObject("counts") ?: JSONObject()
        val by = o.optJSONObject("shared_by")
        return PostItem(
            key = o.optString("item", o.optString("id")), id = o.optString("id"),
            alias = if (o.isNull("alias")) "" else o.optString("alias"),
            name = acc.optString("name").ifBlank { acc.optString("handle") },
            handle = acc.optString("handle"), created = o.optString("created"),
            text = o.optString("text"), warning = o.optString("warning"),
            unread = o.optBoolean("unread"),
            sharedBy = by?.let { it.optString("name").ifBlank { it.optString("handle") } } ?: "",
            contextHandle = ctx?.optString("handle") ?: "",
            contextText = ctx?.optString("text") ?: "",
            replies = counts.optInt("replies"), shares = counts.optInt("shares"),
            likes = counts.optInt("likes"),
        )
    }
}
