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

/** What stands over the lane: a thread, the editor, the config, sync. Back closes it. */
sealed interface Place {
    data class Thread(val focus: String) : Place
    data class Compose(val replyTo: PostItem?) : Place
    data object Config : Place
    data object Sync : Place
}

data class LaneItem(val name: String, val title: String, val unread: Int, val group: String?)

data class PostItem(
    val key: String, val id: String, val sid: String, val alias: String, val name: String,
    val handle: String, val created: String, val text: String, val warning: String,
    val unread: Boolean, val sharedBy: String, val contextHandle: String,
    val contextText: String, val replies: Int, val shares: Int, val likes: Int,
    val liked: Boolean, val number: Int?, val depth: Int,
)

/** What the screens show and what they ask of the core; lives as long as the app's task. */
class AppModel(app: Application) : AndroidViewModel(app) {
    var screen by mutableStateOf<Screen>(Screen.Starting)
    var demo by mutableStateOf(false)
    var handle by mutableStateOf("")
    var newestFirst by mutableStateOf(false)
    var markOnScroll by mutableStateOf(true)
    var defaultVisibility by mutableStateOf("followers")

    var lanes by mutableStateOf(listOf<LaneItem>())
    var current by mutableStateOf<String?>(null)
    var title by mutableStateOf("")
    var posts by mutableStateOf(listOf<PostItem>())
    var divider by mutableStateOf<Pair<String, String>?>(null) // (post key, "new below · N")
    var opening by mutableStateOf(0) // grows each time a lane opens anew: the list re-aims
    var refreshing by mutableStateOf(false)
    var message by mutableStateOf<String?>(null)

    var places by mutableStateOf(listOf<Place>())
    val place: Place? get() = places.lastOrNull()

    var threadPosts by mutableStateOf(listOf<PostItem>())
    var threadOpening by mutableStateOf(0)

    var composeText by mutableStateOf("")
    var composeVisibility by mutableStateOf<String?>(null) // null: the core decides (a reply)
    var sending by mutableStateOf(false)

    var configText by mutableStateOf("")
    var configError by mutableStateOf<String?>(null)
    var saving by mutableStateOf(false)

    var syncInfo by mutableStateOf<JSONObject?>(null)
    var syncKeyShown by mutableStateOf("")
    var syncLoginWaiting by mutableStateOf(false)
    var syncBusy by mutableStateOf(false)

    var loginServer by mutableStateOf("")
    var loginWaiting by mutableStateOf(false)
    var loginNeedsCode by mutableStateOf(false)
    var loginBusy by mutableStateOf(false)

    private var started = false
    private var version = -1
    private var watcher: Job? = null
    private var threadOnStart: String? = null

    fun start(demo: Boolean, openThread: String? = null) {
        if (started) return
        started = true
        this.demo = demo
        threadOnStart = openThread
        viewModelScope.launch {
            val lang = Locale.getDefault().language
            val info = Core.start(getApplication(), lang, demo)
            if (info.has("error")) {
                screen = Screen.Failed(info.optString("error") + "\n\n" + info.optString("trace"))
                return@launch
            }
            afterStart()
        }
    }

    private suspend fun afterStart() {
        val st = Core.state()
        when {
            Core.failed(st) != null -> screen = Screen.Failed(Core.failed(st)!!)
            st.optBoolean("logged_in") -> openMain()
            else -> screen = Screen.Login
        }
    }

    // ---- logging in --------------------------------------------------------------------
    fun beginLogin(openBrowser: (String) -> Unit) {
        if (loginBusy || loginServer.isBlank()) return
        loginBusy = true
        viewModelScope.launch {
            val got = Core.loginBegin(loginServer)
            loginBusy = false
            Core.failed(got)?.let { message = it; return@launch }
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
            Core.failed(got)?.let { message = it; return@launch }
            loginWaiting = false
            openMain()
        }
    }

    // ---- reading -----------------------------------------------------------------------
    private suspend fun openMain() {
        val got = Core.open()
        Core.failed(got)?.let { screen = Screen.Failed(it); return }
        val me = got.optJSONObject("me") ?: JSONObject()
        handle = me.optString("handle")
        newestFirst = me.optString("order") == "newest_first"
        markOnScroll = me.optString("mark_read", "on_scroll") == "on_scroll"
        defaultVisibility = me.optString("visibility", "followers")
        val arr = got.optJSONArray("lanes") ?: JSONArray()
        lanes = parseLanes(arr)
        val first = (0 until arr.length()).map { arr.getJSONObject(it) }
            .firstOrNull { it.optBoolean("start") }?.optString("name")
            ?: lanes.firstOrNull { it.name == "home" }?.name ?: lanes.firstOrNull()?.name
        screen = Screen.Main
        first?.let { showLane(it) }
        watch()
        threadOnStart?.let { openThread(it) }
        threadOnStart = null
    }

    fun showLane(name: String) {
        current = name
        places = emptyList()
        viewModelScope.launch { loadLane(name, keep = false) }
    }

    private suspend fun loadLane(name: String, keep: Boolean) {
        val got = Core.lane(name, keep)
        Core.failed(got)?.let { message = it; return }
        if (name != current) return // the reader moved on meanwhile
        title = got.optString("title")
        var list = parsePosts(got.optJSONArray("posts"))
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

    fun markRead(keys: Collection<String>, inThread: Boolean = false) {
        val list = if (inThread) threadPosts else posts
        val ids = list.filter { it.key in keys && it.unread }.map { it.id }
        if (ids.isEmpty()) return
        val seen = { p: PostItem -> if (p.id in ids) p.copy(unread = false) else p }
        posts = posts.map(seen)
        threadPosts = threadPosts.map(seen)
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

    // ---- places over the lane ----------------------------------------------------------
    fun back(): Boolean {
        if (places.isEmpty()) return false
        places = places.dropLast(1)
        return true
    }

    fun openThread(postId: String) {
        places = places + Place.Thread(postId)
        threadPosts = emptyList()
        viewModelScope.launch {
            val got = Core.thread(postId)
            Core.failed(got)?.let { message = it; back(); return@launch }
            threadPosts = parsePosts(got.optJSONArray("posts"))
            threadOpening += 1
        }
    }

    fun compose(replyTo: PostItem?) {
        composeText = replyTo?.let { if (it.handle.isNotBlank()) "@${it.handle} " else "" } ?: ""
        composeVisibility = if (replyTo == null) defaultVisibility else null
        places = places + Place.Compose(replyTo)
    }

    fun send() {
        val p = place as? Place.Compose ?: return
        if (composeText.isBlank() || sending) return
        sending = true
        viewModelScope.launch {
            val body = JSONObject().put("text", composeText)
            p.replyTo?.let { body.put("reply_to", it.sid) }
            composeVisibility?.let { body.put("visibility", it) }
            val got = Core.post(body)
            sending = false
            Core.failed(got)?.let { message = it; return@launch }
            composeText = ""
            back()
            (place as? Place.Thread)?.let { reloadThread(it.focus) }
            Core.refresh()
        }
    }

    private suspend fun reloadThread(focus: String) {
        val got = Core.thread(focus)
        if (Core.failed(got) == null) threadPosts = parsePosts(got.optJSONArray("posts"))
    }

    fun like(p: PostItem) {
        viewModelScope.launch {
            val got = Core.act("like", p.sid)
            Core.failed(got)?.let { message = it; return@launch }
            val now = parsePost(got)
            val swap = { x: PostItem ->
                if (x.sid == p.sid) x.copy(liked = now.liked, likes = now.likes) else x
            }
            posts = posts.map(swap)
            threadPosts = threadPosts.map(swap)
        }
    }

    // ---- the config, edited here ---------------------------------------------------------
    fun openConfig() {
        configError = null
        places = places + Place.Config
        viewModelScope.launch {
            val got = Core.configText()
            Core.failed(got)?.let { configError = it; return@launch }
            configText = got.optString("text")
        }
    }

    fun saveConfig() {
        if (saving) return
        saving = true
        viewModelScope.launch {
            val got = Core.configSave(configText)
            saving = false
            Core.failed(got)?.let { configError = it; return@launch }
            configError = null
            // the core was made anew with the file: open everything again
            watcher?.cancel()
            version = -1
            places = emptyList()
            screen = Screen.Starting
            afterStart()
        }
    }

    // ---- sync with the other devices -----------------------------------------------------
    fun openSync() {
        syncKeyShown = ""
        places = places + Place.Sync
        loadSync()
    }

    private fun loadSync() {
        viewModelScope.launch { syncInfo = Core.syncStatus() }
    }

    fun syncLogin(openBrowser: (String) -> Unit) {
        viewModelScope.launch {
            val got = Core.syncLoginBegin()
            Core.failed(got)?.let { message = it; return@launch }
            syncLoginWaiting = true
            openBrowser(got.optString("url"))
        }
    }

    fun syncLoginCode(code: String) {
        viewModelScope.launch {
            val got = Core.syncLoginFinish(code)
            Core.failed(got)?.let { message = it; return@launch }
            syncLoginWaiting = false
            loadSync()
        }
    }

    fun syncShowKey() {
        viewModelScope.launch {
            val got = Core.syncKey()
            Core.failed(got)?.let { message = it; return@launch }
            syncKeyShown = got.optString("key")
        }
    }

    fun syncJoin(key: String) {
        viewModelScope.launch {
            val got = Core.syncJoin(key)
            Core.failed(got)?.let { message = it; return@launch }
            loadSync()
        }
    }

    fun syncNow(done: (String) -> Unit) {
        if (syncBusy) return
        syncBusy = true
        viewModelScope.launch {
            val got = Core.syncNow()
            syncBusy = false
            Core.failed(got)?.let { message = it }
            if (!got.has("error")) {
                done(if (got.optBoolean("failed")) ""
                     else "${got.optInt("sent")} / ${got.optInt("got")}")
            }
            loadSync()
        }
    }

    // ---- JSON → items ------------------------------------------------------------------
    private fun parseLanes(arr: JSONArray) = (0 until arr.length()).map {
        val o = arr.getJSONObject(it)
        LaneItem(o.optString("name"), o.optString("title"), o.optInt("unread"),
            if (o.isNull("group")) null else o.optString("group"))
    }

    private fun parsePosts(arr: JSONArray?): List<PostItem> =
        if (arr == null) emptyList() else (0 until arr.length()).map { parsePost(arr.getJSONObject(it)) }

    private fun parsePost(o: JSONObject): PostItem {
        val acc = o.optJSONObject("account") ?: JSONObject()
        val ctx = o.optJSONObject("context")
        val counts = o.optJSONObject("counts") ?: JSONObject()
        val mine = o.optJSONObject("mine") ?: JSONObject()
        val by = o.optJSONObject("shared_by")
        return PostItem(
            key = o.optString("item", o.optString("id")), id = o.optString("id"),
            sid = o.optString("sid", o.optString("id")),
            alias = if (o.isNull("alias")) "" else o.optString("alias"),
            name = acc.optString("name").ifBlank { acc.optString("handle") },
            handle = acc.optString("handle"), created = o.optString("created"),
            text = o.optString("text"), warning = o.optString("warning"),
            unread = o.optBoolean("unread"),
            sharedBy = by?.let { it.optString("name").ifBlank { it.optString("handle") } } ?: "",
            contextHandle = ctx?.optString("handle") ?: "",
            contextText = ctx?.optString("text") ?: "",
            replies = counts.optInt("replies"), shares = counts.optInt("shares"),
            likes = counts.optInt("likes"), liked = mine.optBoolean("liked"),
            number = if (o.has("number") && !o.isNull("number")) o.optInt("number") else null,
            depth = o.optInt("depth"),
        )
    }
}
