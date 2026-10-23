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

/** What stands over the lanes: a thread, the editor, pictures, the config, sync. Back closes it. */
sealed interface Place {
    data class Thread(val focus: String) : Place
    data class Compose(val replyTo: PostItem?) : Place
    data class Media(val items: List<MediaItem>, val index: Int) : Place
    data object Settings : Place
    data object Config : Place
    data object Sync : Place
}

/** One option of the settings page: the config file's, with its explanation. value and
 *  dflt as JSON text ("\"tiles\"", "true", "[\"home\"]"), to compare and to write back. */
data class Setting(
    val section: String, val key: String, val type: String, val value: String,
    val dflt: String, val choices: List<String>?, val help: String,
)

data class SettingsChapter(val title: String, val options: List<Setting>)

data class LaneItem(val name: String, val title: String, val unread: Int, val group: String?)

/** The overview's row: a lane, its count, who and what its first unread post is. */
data class HubLane(val name: String, val title: String, val unread: Int, val peek: String)

/** kind: you | reading | lists | browse (bridge.hub) */
data class HubSection(val kind: String, val lanes: List<HubLane>)

data class MediaItem(
    val kind: String, val preview: String, val url: String, val alt: String,
    val w: Int, val h: Int,
)

data class LinkCard(val url: String, val title: String, val provider: String, val image: String)

data class PostItem(
    val key: String, val id: String, val sid: String, val alias: String, val name: String,
    val handle: String, val avatar: String, val created: String, val text: String,
    val warning: String, val sensitive: Boolean, val media: List<MediaItem>,
    val card: LinkCard?, val poll: String, val html: String, val url: String,
    val shared: Boolean, val bookmarked: Boolean,
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
    var hideSensitive by mutableStateOf(true)
    var commandLine by mutableStateOf(false)
    var overview by mutableStateOf("tiles") // phone.overview: tiles | list
    var layoutPref by mutableStateOf("auto") // phone.layout: auto | one | two | three
    var columns = 1                          // what the screen fits now (Screens.kt says)
    private var startLane: String? = null

    var lanes by mutableStateOf(listOf<LaneItem>())
    var hub by mutableStateOf(listOf<HubSection>())
    var hubOrder by mutableStateOf(listOf<String>()) // lanes with news, in reading order
    var hubUnread by mutableStateOf(0)
    var hubWithNews by mutableStateOf(0)
    var hubPinned by mutableStateOf(listOf<String>()) // phone.pinned, as lanes here

    var current by mutableStateOf<String?>(null) // null: the overview of lanes
    var title by mutableStateOf("")
    var posts by mutableStateOf(listOf<PostItem>())
    var divider by mutableStateOf<Pair<String, String>?>(null) // (post key, "new below · N")
    var opening by mutableStateOf(0) // grows each time a lane opens anew: the list re-aims
    var aimed = 0                     // the opening the list last aimed at
    var refreshing by mutableStateOf(false) // asked by ⟳: a thin bar under the title
    var pulling by mutableStateOf(false)    // asked by pulling the list down
    var message by mutableStateOf<String?>(null)

    var places by mutableStateOf(listOf<Place>())
    val place: Place? get() = places.lastOrNull()

    var threadPosts by mutableStateOf(listOf<PostItem>())
    var threadOpening by mutableStateOf(0)

    var composeText by mutableStateOf("")
    var composeVisibility by mutableStateOf<String?>(null) // null: the core decides (a reply)
    var sending by mutableStateOf(false)

    var cmdText by mutableStateOf("")
    var cmdHint by mutableStateOf("")
    var cmdConfirm by mutableStateOf<String?>(null) // "delete this?" — asked before doing
    var cmdBusy by mutableStateOf(false)

    var settings by mutableStateOf(listOf<SettingsChapter>())

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
    private var laneOnStart: String? = null

    private var settingsOnStart = false

    fun start(
        demo: Boolean, openThread: String? = null, openLane: String? = null,
        openSettings: Boolean = false,
    ) {
        if (started) return
        started = true
        settingsOnStart = openSettings
        this.demo = demo
        threadOnStart = openThread
        laneOnStart = openLane
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

    // ---- the overview and the lanes ------------------------------------------------------
    private suspend fun openMain() {
        val got = Core.open()
        Core.failed(got)?.let { screen = Screen.Failed(it); return }
        val me = got.optJSONObject("me") ?: JSONObject()
        handle = me.optString("handle")
        newestFirst = me.optString("order") == "newest_first"
        markOnScroll = me.optString("mark_read", "on_scroll") == "on_scroll"
        defaultVisibility = me.optString("visibility", "followers")
        hideSensitive = me.optString("sensitive_media", "hide") != "show"
        commandLine = me.optBoolean("command_line")
        overview = me.optString("overview", "tiles")
        layoutPref = me.optString("layout", "auto")
        val arr = got.optJSONArray("lanes") ?: JSONArray()
        lanes = parseLanes(arr)
        startLane = (0 until arr.length()).map { arr.getJSONObject(it) }
            .firstOrNull { it.optBoolean("start") }?.optString("name")
            ?: lanes.firstOrNull { it.name == "home" }?.name ?: lanes.firstOrNull()?.name
        loadHub()
        current = null
        screen = Screen.Main
        laneOnStart?.let { showLane(it) }
        laneOnStart = null
        watch()
        threadOnStart?.let { openThread(it) }
        threadOnStart = null
        if (settingsOnStart) openSettings()
        settingsOnStart = false
    }

    private suspend fun loadHub() {
        val got = Core.hub()
        if (Core.failed(got) != null) return
        val secs = got.optJSONArray("sections") ?: JSONArray()
        hub = (0 until secs.length()).map { i ->
            val s = secs.getJSONObject(i)
            val arr = s.optJSONArray("lanes") ?: JSONArray()
            HubSection(s.optString("key"), (0 until arr.length()).map { j ->
                val l = arr.getJSONObject(j)
                HubLane(l.optString("name"), l.optString("title"), l.optInt("unread"),
                    l.optString("peek"))
            })
        }
        val order = got.optJSONArray("order") ?: JSONArray()
        hubOrder = (0 until order.length()).map { order.getString(it) }
        val pin = got.optJSONArray("pinned") ?: JSONArray()
        hubPinned = (0 until pin.length()).map { pin.getString(it) }
        hubUnread = got.optInt("unread")
        hubWithNews = got.optInt("with_news")
    }

    /** The tiles: phone.pinned in its order, or (none pinned) every lane with a count;
     *  each with "is it yours" (tinted when there's news). */
    fun tileLanes(): List<Pair<HubLane, Boolean>> {
        val all = hub.flatMap { s -> s.lanes.map { it to (s.kind == "you") } }
        if (hubPinned.isEmpty()) return all.filter { (l, _) -> hub.any { s -> s.kind != "browse" && l in s.lanes } }
        return hubPinned.mapNotNull { name -> all.firstOrNull { it.first.name == name } }
    }

    /** Under the tiles, as rows: (lane, only browsed — no count). */
    fun restLanes(): List<Pair<HubLane, Boolean>> {
        val tiles = tileLanes().map { it.first.name }.toSet()
        return hub.flatMap { s -> s.lanes.map { it to (s.kind == "browse") } }
            .filter { it.first.name !in tiles }
            .sortedBy { if (it.second) 1 else 0 }
    }

    fun laneTitle(name: String): String =
        hub.flatMap { it.lanes }.firstOrNull { it.name == name }?.title
            ?: lanes.firstOrNull { it.name == name }?.title ?: name

    fun unreadOf(name: String): Int = hub.flatMap { it.lanes }.firstOrNull { it.name == name }?.unread ?: 0

    /** The next lane with news after this one, in reading order (yours first): or null. */
    fun nextLane(after: String? = current): HubLane? {
        val all = hub.filter { it.kind != "browse" }.flatMap { it.lanes }
        val names = all.map { it.name }
        val from = after?.let { names.indexOf(it) } ?: -1
        val rest = all.drop(from + 1) + all.take(maxOf(from, 0))
        return rest.firstOrNull { it.unread > 0 && it.name != after }
    }

    /** Columns side by side: the lane pane never stands empty — the lane of last time. */
    fun openStartLane() {
        if (current == null) (startLane ?: lanes.firstOrNull()?.name)?.let { showLane(it) }
    }

    fun readInRow() {
        nextLane(after = null)?.let { showLane(it.name) }
    }

    fun showLane(name: String) {
        current = name
        title = laneTitle(name)
        posts = emptyList()
        divider = null
        places = emptyList()
        viewModelScope.launch { loadLane(name, keep = false) }
    }

    fun toOverview() {
        current = null
        places = emptyList()
        viewModelScope.launch { loadHub() }
    }

    private suspend fun loadLane(name: String, keep: Boolean) {
        val got = Core.lane(name, keep)
        Core.failed(got)?.let { message = it; return }
        if (name != current) return // the reader moved on meanwhile
        title = got.optString("title").ifBlank { laneTitle(name) }
        var list = parsePosts(got.optJSONArray("posts"))
        if (newestFirst) list = list.reversed()
        posts = list
        val div = got.optJSONObject("divider")
        divider = div?.let { d ->
            list.firstOrNull { it.id == d.optString("before") }?.key?.let { it to d.optString("text") }
        }
        if (!keep) opening += 1
    }

    fun refresh(pulled: Boolean = false) {
        if (pulled) pulling = true else refreshing = true
        viewModelScope.launch {
            Core.refresh()
            delay(if (pulled) 1500 else 8000) // the round's news come through watch()
            pulling = false
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
                    loadHub()
                    current?.let { loadLane(it, keep = true) }
                    refreshing = false
                    pulling = false
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
    /** Back: the place on top closes; with none, a lane goes back to the overview. */
    fun back(): Boolean {
        if (places.isNotEmpty()) {
            val left = places.last()
            places = places.dropLast(1)
            if (left == Place.Settings) applySettings()
            if (left == Place.Config && place == Place.Settings) {
                viewModelScope.launch { loadSettings() } // the file was edited by hand
            }
            return true
        }
        if (current != null && columns == 1) {
            toOverview()
            return true
        }
        return false
    }

    fun openThread(postId: String) {
        // three columns: the thread pane shows one thread — a new one takes its place
        val keep = if (columns >= 3 && place is Place.Thread) places.dropLast(1) else places
        places = keep + Place.Thread(postId)
        threadPosts = emptyList()
        viewModelScope.launch {
            val got = Core.thread(postId)
            Core.failed(got)?.let { message = it; back(); return@launch }
            threadPosts = parsePosts(got.optJSONArray("posts"))
            threadOpening += 1
        }
    }

    fun openMedia(items: List<MediaItem>, index: Int) {
        places = places + Place.Media(items, index)
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
            places = places.dropLast(1)
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

    /** like / share / bookmark, toggled; the card takes what the server says now. */
    fun act(p: PostItem, action: String) {
        viewModelScope.launch {
            val got = Core.act(action, p.sid)
            Core.failed(got)?.let { message = it; return@launch }
            val now = parsePost(got)
            val swap = { x: PostItem ->
                if (x.sid == p.sid) x.copy(liked = now.liked, likes = now.likes, shared = now.shared,
                    shares = now.shares, bookmarked = now.bookmarked) else x
            }
            posts = posts.map(swap)
            threadPosts = threadPosts.map(swap)
        }
    }

    /** A card's ⋯: whether its thread is followed, its address. */
    suspend fun menuOf(p: PostItem): JSONObject = Core.menu(p.sid)

    fun threadAct(p: PostItem, action: String) {
        viewModelScope.launch {
            val got = Core.threadAct(action, p.sid)
            message = Core.failed(got) ?: got.optString("message").ifBlank { null }
        }
    }

    /** A link tapped in a post: a post my server knows opens as a thread; else the browser. */
    fun openLink(url: String, openBrowser: (String) -> Unit) {
        viewModelScope.launch {
            val got = Core.resolve(url)
            if (got.optString("found") == "thread" && got.optString("id").isNotBlank()) {
                openThread(got.optString("id"))
            } else {
                openBrowser(url)
            }
        }
    }

    // ---- Point's command line (ui.command_line; off on the phone by default) --------------
    fun cmdChanged(text: String) {
        cmdText = text
    }

    suspend fun cmdPreview(text: String) {
        val got = Core.commandPreview(text)
        cmdHint = if (Core.failed(got) == null) got.optString("text") else ""
    }

    fun putAlias(alias: String) {
        if (!commandLine || alias.isBlank()) return
        val rest = cmdText.replace(Regex("^#\\S+\\s*"), "")
        cmdText = "#$alias " + rest
    }

    fun runCommand(confirmed: Boolean = false) {
        val line = cmdText
        if (line.isBlank() || cmdBusy) return
        cmdBusy = true
        cmdConfirm = null
        viewModelScope.launch {
            val got = Core.command(line, confirmed)
            cmdBusy = false
            Core.failed(got)?.let { message = it; return@launch }
            got.optString("confirm").takeIf { it.isNotBlank() }?.let { cmdConfirm = it; return@launch }
            if (got.optBoolean("ok")) {
                cmdText = ""
                cmdHint = ""
            }
            got.optString("message").takeIf { it.isNotBlank() }?.let { message = it }
            got.optJSONObject("open")?.let { o ->
                o.optString("thread").takeIf { it.isNotBlank() }?.let { openThread(it) }
            }
            Core.refresh()
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

    // ---- the settings page: the config's options, written into the file one by one ------
    var settingsQuery = "" // what the page's search starts with ("pinned" from "change")

    fun openSettings(query: String = "") {
        settingsQuery = query
        places = places + Place.Settings
        viewModelScope.launch { loadSettings() }
    }

    private suspend fun loadSettings() {
        val got = Core.settings()
        Core.failed(got)?.let { message = it; return }
        val chs = got.optJSONArray("chapters") ?: JSONArray()
        settings = (0 until chs.length()).map { i ->
            val c = chs.getJSONObject(i)
            val opts = c.optJSONArray("options") ?: JSONArray()
            SettingsChapter(c.optString("title"), (0 until opts.length()).map { j ->
                val o = opts.getJSONObject(j)
                val ch = o.optJSONArray("choices")
                Setting(o.optString("section"), o.optString("key"), o.optString("type"),
                    jsonText(o.opt("value")), jsonText(o.opt("default")),
                    ch?.let { a -> (0 until a.length()).map { a.getString(it) } },
                    o.optString("help"))
            })
        }
    }

    /** One option into the file (checked there first); the page shows what it is now. */
    fun setSetting(opt: Setting, json: String) {
        viewModelScope.launch {
            val got = Core.settingSet(opt.section, opt.key, json)
            Core.failed(got)?.let { message = it; return@launch }
            val now = jsonText(got.opt("value"))
            settings = settings.map { c ->
                c.copy(options = c.options.map {
                    if (it.section == opt.section && it.key == opt.key) it.copy(value = now) else it
                })
            }
        }
    }

    /** Leaving the page: what changed takes effect — the core made anew, once. */
    private fun applySettings() {
        viewModelScope.launch {
            val got = Core.settingsApply()
            if (got.optBoolean("restarted")) restartScreens()
        }
    }

    private suspend fun restartScreens() {
        watcher?.cancel()
        version = -1
        places = emptyList()
        current = null
        screen = Screen.Starting
        afterStart()
    }

    fun saveConfig() {
        if (saving) return
        saving = true
        viewModelScope.launch {
            val got = Core.configSave(configText)
            saving = false
            Core.failed(got)?.let { configError = it; return@launch }
            configError = null
            restartScreens() // the core was made anew with the file: open everything again
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
    private fun jsonText(x: Any?): String = when (x) {
        null, JSONObject.NULL -> "null"
        is String -> JSONObject.quote(x)
        else -> x.toString()
    }

    private fun parseLanes(arr: JSONArray) = (0 until arr.length()).map {
        val o = arr.getJSONObject(it)
        LaneItem(o.optString("name"), o.optString("title"), o.optInt("unread"),
            if (o.isNull("group")) null else o.optString("group"))
    }

    private fun parsePosts(arr: JSONArray?): List<PostItem> =
        if (arr == null) emptyList() else (0 until arr.length()).map { parsePost(arr.getJSONObject(it)) }

    private fun str(o: JSONObject?, key: String): String =
        if (o == null || o.isNull(key)) "" else o.optString(key)

    private fun parsePost(o: JSONObject): PostItem {
        val acc = o.optJSONObject("account") ?: JSONObject()
        val ctx = o.optJSONObject("context")
        val counts = o.optJSONObject("counts") ?: JSONObject()
        val mine = o.optJSONObject("mine") ?: JSONObject()
        val by = o.optJSONObject("shared_by")
        val media = o.optJSONArray("media") ?: JSONArray()
        val card = o.optJSONObject("card")
        val poll = o.optJSONObject("poll")
        return PostItem(
            key = o.optString("item", o.optString("id")), id = o.optString("id"),
            sid = o.optString("sid", o.optString("id")),
            alias = str(o, "alias"),
            name = str(acc, "name").ifBlank { str(acc, "handle") },
            handle = str(acc, "handle"), avatar = str(acc, "avatar"),
            created = str(o, "created"),
            text = str(o, "text").trim(), warning = str(o, "warning"),
            sensitive = o.optBoolean("sensitive"),
            media = (0 until media.length()).map {
                val m = media.getJSONObject(it)
                MediaItem(str(m, "kind"), str(m, "preview"), str(m, "url"), str(m, "alt"),
                    m.optInt("w"), m.optInt("h"))
            }.filter { it.preview.isNotBlank() || it.url.isNotBlank() },
            card = card?.let { LinkCard(str(it, "url"), str(it, "title"), str(it, "provider"),
                str(it, "image")) },
            poll = poll?.let { p ->
                val opts = p.optJSONArray("options") ?: JSONArray()
                ((0 until opts.length()).map {
                    val x = opts.getJSONObject(it)
                    "${str(x, "title")} — ${x.optInt("share")}%"
                } + str(p, "summary")).filter { it.isNotBlank() }.joinToString("\n")
            } ?: "",
            html = str(o, "html"), url = str(o, "url"),
            shared = mine.optBoolean("shared"), bookmarked = mine.optBoolean("bookmarked"),
            unread = o.optBoolean("unread"),
            sharedBy = by?.let { str(it, "name").ifBlank { str(it, "handle") } } ?: "",
            contextHandle = str(ctx, "handle"),
            contextText = str(ctx, "text"),
            replies = counts.optInt("replies"), shares = counts.optInt("shares"),
            likes = counts.optInt("likes"), liked = mine.optBoolean("liked"),
            number = if (o.has("number") && !o.isNull("number")) o.optInt("number") else null,
            depth = o.optInt("depth"),
        )
    }
}
