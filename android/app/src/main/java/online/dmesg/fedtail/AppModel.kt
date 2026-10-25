package online.dmesg.fedtail

import android.app.Application
import android.content.ClipData
import android.content.ClipboardManager
import android.net.Uri
import android.webkit.MimeTypeMap
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.withContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
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
    /** init: what the core put in the editor (an edit of my post, a quote, a text). */
    data class Compose(val replyTo: PostItem?, val init: JSONObject? = null) : Place
    /** Any place of the windows' ≡ menu (common/places.py): search, lists, the server… */
    data class Page(val name: String, val arg: String = "", val tab: String = "",
                    val cursor: String = "") : Place
    /** Someone's profile; show: posts | all | media (null — feed.profile_show). */
    data class Profile(val id: String, val show: String? = null) : Place
    /** The places, as the windows' ≡ menu lists them. */
    data object Menu : Place
    data class Media(val items: List<MediaItem>, val index: Int) : Place
    data object Settings : Place
    data object SelfCheck : Place
    data object Config : Place
    data object Sync : Place
}

/** One option of the settings page — the desktop's settings window's (common/settings.py):
 *  kind bool | int | text | choice | checks | list; value, dflt and each choice's value as
 *  JSON text ("\"tiles\"", "true", "[\"home\"]"), to compare and to write back. */
data class Setting(
    val section: String, val key: String, val kind: String, val title: String,
    val about: String, val value: String, val dflt: String,
    val choices: List<Pair<String, String>>, val changed: Boolean, val group: String,
)

data class SettingsChapter(val title: String, val options: List<Setting>)

data class LaneItem(val name: String, val title: String, val unread: Int, val group: String?)

/** The overview's row: a lane, its count, who and what its first unread post is. */
data class HubLane(
    val name: String, val title: String, val unread: Int, val peek: String,
    val capped: Boolean = false, // as many unread as the lane holds: maybe more past them
) {
    /** The count as shown: "300+" when there may be more than the lane holds. */
    val count: String get() = if (capped) "$unread+" else "$unread"
}

/** kind: you | reading | lists | browse (bridge.hub) */
data class HubSection(val kind: String, val lanes: List<HubLane>)

data class MediaItem(
    val kind: String, val preview: String, val url: String, val alt: String,
    val w: Int, val h: Int,
)

/** A button of a place (common/places.py Btn): act = [place, key, data]. */
data class PlaceButton(val label: String, val act: List<String>, val primary: Boolean, val tip: String)

/** A row of a place shown in a lane's stead (activity, follow requests): the windows' rows. */
data class PlaceRow(val title: String, val line: String, val key: String,
                    val buttons: List<PlaceButton>, val fresh: Boolean)

/** Activity, follow requests: rows with buttons, "nothing yet", the place's own buttons. */
data class PlacePage(val rows: List<PlaceRow>, val empty: String,
                     val submit: PlaceButton?, val more: PlaceButton?)

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
    val accountId: String = "",
    val pollOptions: List<String> = emptyList(), // a poll's options, to vote on
    val pollMultiple: Boolean = false,
    val pollOpen: Boolean = false,               // not voted, not over, not mine: votable
    val own: Boolean = false,
    val edited: Boolean = false,
    val quoteId: String = "",        // the post it quotes, or a note why it can't be shown
    val quoteWho: String = "",
    val quoteText: String = "",
)

/** A question the core asked, to answer in a dialog. */
sealed interface Asking {
    /** "Sure?" — yes runs again confirmed. */
    data class Confirm(val text: String, val yes: () -> Unit, val title: String = "",
                       val yesLabel: String = "", val noLabel: String = "") : Asking
    /** One of a few answers, maybe a box to tick (how long a mute lasts…). */
    data class Choose(val title: String, val text: String, val options: List<Pair<String, String>>,
                      val check: String, val pick: (String, Boolean) -> Unit) : Asking
    /** A line to type (a list's new name, a note…). */
    data class Text(val title: String, val question: String, val text: String,
                    val done: (String) -> Unit) : Asking
}

data class AccountItem(val id: String, val handle: String, val name: String, val avatar: String)

/** A form's field (common/places.py Field): kind line | text | check | choice | checks | file. */
data class PageField(val name: String, val label: String, val kind: String, val value: Any?,
                     val choices: List<Pair<String, String>>, val tip: String)

/** A place's row: kind item | post | account | tag | text | heading | html. */
data class PageRow(val kind: String, val title: String, val line: String, val key: String,
                   val buttons: List<PlaceButton>, val post: PostItem?, val account: AccountItem?,
                   val html: String)

/** A place as the windows draw it: the hint, the tabs, the rows, the form and its button. */
data class PageView(
    val name: String, val title: String, val arg: String, val hint: String,
    val tabs: List<Pair<String, String>>, val tab: String, val rows: List<PageRow>,
    val form: List<PageField>, val submit: PlaceButton?, val more: PlaceButton?, val empty: String,
)

/** "Often writes about: #a, #b", "Recommends: @x": tags and people open here. */
data class FeaturedLine(val title: String, val text: String, val tags: List<String>,
                        val people: List<AccountItem>)

/** "More" under a profile's posts: my server's next page (cursor ""), then theirs. */
data class OlderOffer(val label: String, val cursor: String)

data class ProfileButton(val key: String, val label: String, val tip: String, val primary: Boolean)

/** Someone's profile: the web page's (common/profile.py), with their posts. */
data class ProfileView(
    val account: AccountItem, val note: String, val header: String, val counts: String,
    val fields: List<Triple<String, String, Boolean>>, val own: Boolean, val meta: List<String>,
    val noteLine: String, val actions: List<ProfileButton>,
    val shows: List<Triple<String, String, Boolean>>, val showTip: String,
    val posts: List<PostItem>,
    val pinned: Set<String> = emptySet(),          // keys of the pinned posts on top
    val featured: List<FeaturedLine> = emptyList(),
    val familiar: String = "",
    val moved: Pair<String, AccountItem>? = null,  // "moved to @new", and who
    val movedOpen: String = "",
    val older: OlderOffer? = null,
    val maxId: String = "",
    val loadingMore: Boolean = false,
)

/** An attachment in the editor: uploaded (token) or one of my post's (id, when editing). */
data class Attachment(val token: String, val name: String, val kind: String,
                      val alt: String = "", val id: String = "", val preview: String = "")

/** What the screens show and what they ask of the core; lives as long as the app's task. */
class AppModel(app: Application) : AndroidViewModel(app) {
    var screen by mutableStateOf<Screen>(Screen.Starting)
    var demo by mutableStateOf(false)
    var handle by mutableStateOf("")
    var newestFirst by mutableStateOf(false)
    var markOnScroll by mutableStateOf(true)
    var defaultVisibility by mutableStateOf("followers")
    var hideSensitive by mutableStateOf(true)
    var expandCw by mutableStateOf(false) // config.expand_cw: ui.expand_cw, or ui.arts_mode
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
    var placePage by mutableStateOf<PlacePage?>(null) // activity, requests: rows, not posts
    var placeConfirm by mutableStateOf<Pair<String, PlaceButton>?>(null) // "sure?" first
    var opening by mutableStateOf(0) // grows each time a lane opens anew: the list re-aims
    var aimed = 0                     // the opening the list last aimed at
    var refreshing by mutableStateOf(false) // asked by ⟳: a thin bar under the title
    var pulling by mutableStateOf(false)    // asked by pulling the list down
    var message by mutableStateOf<String?>(null)

    var places by mutableStateOf(listOf<Place>())
    val place: Place? get() = places.lastOrNull()

    var threadPosts by mutableStateOf(listOf<PostItem>())
    var threadOpening by mutableStateOf(0) // grows when the thread should be aimed anew
    var threadAimed = 0                    // the opening the thread list last aimed at
    var threadAimAt: String? = null        // where to stand then: a reply just sent

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
    private var pageOnStart: String? = null    // the screenshots' places (demo only)
    private var profileOnStart: String? = null
    private var composeOnStart = false

    fun start(
        demo: Boolean, openThread: String? = null, openLane: String? = null,
        openSettings: Boolean = false, openPage: String? = null, openProfile: String? = null,
        openCompose: Boolean = false,
    ) {
        if (started) return
        started = true
        pageOnStart = openPage
        profileOnStart = openProfile
        composeOnStart = openCompose
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
    var merged by mutableStateOf(false)      // all accounts in one window
    var accountCount by mutableStateOf(1)

    /** ≡ → All accounts in one window: the core made anew with (or without) the others. */
    fun toggleMerge() {
        viewModelScope.launch {
            val got = Core.merge(!merged)
            Core.failed(got)?.let { message = it; return@launch }
            restartScreens()
        }
    }

    var themeColors by mutableStateOf<Map<String, String>>(emptyMap()) // ui.theme's; {}: system
    var themeLight by mutableStateOf(true)

    var themeFont by mutableStateOf<androidx.compose.ui.text.font.FontFamily?>(null)
    var themeScale by mutableStateOf(1f)
    var themePictures by mutableStateOf<Map<String, ThemePic>>(emptyMap())

    private suspend fun loadTheme() {
        val got = Core.theme()
        if (Core.failed(got) != null) return
        val c = got.optJSONObject("colors") ?: JSONObject()
        themeColors = c.keys().asSequence().associateWith { c.optString(it) }
        themeLight = got.optBoolean("light", true)
        val font = got.optJSONObject("font") ?: JSONObject()
        val text = font.optJSONObject("text")
        themeFont = fontFamilyOf(text?.let { t -> t.keys().asSequence().associateWith { t.optString(it) } })
        themeScale = font.optDouble("scale", 1.0).toFloat().coerceIn(0.8f, 1.6f)
        val pics = Core.pictures()
        themePictures = if (Core.failed(pics) != null) emptyMap() else
            pics.keys().asSequence().associateWith { k ->
                val o = pics.getJSONObject(k)
                ThemePic(o.optString("svg"), o.optString("png"))
            }
    }

    private suspend fun openMain() {
        loadTheme()
        val got = Core.open()
        Core.failed(got)?.let { screen = Screen.Failed(it); return }
        val me = got.optJSONObject("me") ?: JSONObject()
        handle = me.optString("handle")
        newestFirst = me.optString("order") == "newest_first"
        markOnScroll = me.optString("mark_read", "on_scroll") == "on_scroll"
        defaultVisibility = me.optString("visibility", "followers")
        hideSensitive = me.optString("sensitive_media", "hide") != "show"
        expandCw = me.optBoolean("expand_cw")
        commandLine = me.optBoolean("command_line")
        overview = me.optString("overview", "tiles")
        layoutPref = me.optString("layout", "auto")
        merged = me.optBoolean("merged")
        accountCount = me.optInt("accounts", 1)
        // phone.push: UnifiedPush when a distributor is there (not in the demo: no server)
        if (!demo) Push.setUp(getApplication(), me.optString("push", "auto"))
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
        pageOnStart?.let { openPage(it) }
        profileOnStart?.let { openProfile(it) }
        if (composeOnStart) compose(null)
        pageOnStart = null
        profileOnStart = null
        composeOnStart = false
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
                    l.optString("peek"), l.optBoolean("capped"))
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

    var editTiles by mutableStateOf(false) // "change" over the tiles: rows to move / remove

    fun editPins() {
        editTiles = true
        if (columns == 1) toOverview()
    }

    /** Pin or unpin a lane as a tile, or move it (by -1 / +1); [] back means "every lane". */
    fun pinTile(name: String, on: Boolean) {
        val now = tileLanes().map { it.first.name }
        val next = if (on) (if (name in now) now else now + name) else now - name
        savePins(next)
    }

    fun moveTile(name: String, by: Int) {
        val now = tileLanes().map { it.first.name }.toMutableList()
        val i = now.indexOf(name)
        val j = i + by
        if (i < 0 || j < 0 || j >= now.size) return
        now[i] = now[j].also { now[j] = now[i] }
        savePins(now)
    }

    private fun savePins(names: List<String>) {
        hubPinned = names
        viewModelScope.launch {
            Core.failed(Core.pin(names))?.let { message = it }
            loadHub()
        }
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
        placePage = null
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
        placePage = got.optJSONObject("page")?.let { parsePlace(it) }
        if (placePage != null) {
            posts = emptyList()
            laneOlder = false
            divider = null
            loadHub() // on screen the activity is seen: its count goes
            if (!keep) opening += 1
            return
        }
        var list = parsePosts(got.optJSONArray("posts"))
        if (newestFirst) list = list.reversed()
        posts = list
        laneOlder = got.optBoolean("older")
        val div = got.optJSONObject("divider")
        divider = div?.let { d ->
            list.firstOrNull { it.id == d.optString("before") }?.key?.let { it to d.optString("text") }
        }
        if (!keep) opening += 1
    }

    var laneOlder by mutableStateOf(false)   // "earlier" can bring older posts
    var loadingOlder by mutableStateOf(false)

    /** "Earlier" at the lane's top: older posts from the server (history counts as read). */
    fun loadOlder() {
        val name = current ?: return
        if (loadingOlder) return
        loadingOlder = true
        viewModelScope.launch {
            val got = Core.older(name)
            Core.failed(got)?.let { message = it }
            if (got.optInt("n") == 0 && !got.has("error")) laneOlder = false
            loadLane(name, keep = true)
            loadingOlder = false
        }
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
                    // the windows' notes into the shade (notify.when_focused: even now)
                    Notifier.take(getApplication(), Core.notes(Notifier.lastSeq))
                    lanes = parseLanes(Core.lanes())
                    loadHub()
                    current?.let { loadLane(it, keep = true) }
                    refreshing = false
                    pulling = false
                }
            }
        }
    }

    /** A tap on a note in the shade: its thread, or its lane. */
    fun openFromNote(lane: String?, thread: String?) {
        if (screen != Screen.Main) {
            threadOnStart = thread?.takeIf { it.isNotBlank() } ?: threadOnStart
            laneOnStart = lane?.takeIf { it.isNotBlank() } ?: laneOnStart
            return
        }
        when {
            !thread.isNullOrBlank() -> openThread(thread)
            !lane.isNullOrBlank() -> showLane(lane)
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
            if (left is Place.Page && left !in places) pages.remove(left)
            if (left is Place.Profile && left !in places) profiles.remove(left)
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
        clearEditor()
        replyToId = null
        loadEditorFacts()
        composeText = replyTo?.let { if (it.handle.isNotBlank()) "@${it.handle} " else "" } ?: ""
        composeVisibility = if (replyTo == null) defaultVisibility else null
        places = places + Place.Compose(replyTo)
    }

    fun send(altOk: Boolean = false) {
        val p = place as? Place.Compose ?: return
        if (composeText.isBlank() || sending || uploading > 0) return
        sending = true
        viewModelScope.launch {
            val body = JSONObject().put("text", composeText)
            if (composeCwOn && composeCw.isNotBlank()) body.put("cw", composeCw)
            val edit = editId
            if (edit != null) {
                body.put("edit", edit)
                body.put("media_edit", JSONArray(attachments.filter { it.id.isNotBlank() }.map {
                    JSONObject().put("id", it.id).put("alt", it.alt) }))
            } else {
                (p.replyTo?.sid ?: replyToId)?.let { body.put("reply_to", it) }
                composeVisibility?.let { body.put("visibility", it) }
                if (composeLang.isNotBlank()) body.put("lang", composeLang)
                quoteId?.let { body.put("quote", it) }
                val media = attachments.filter { it.token.isNotBlank() }
                if (media.isNotEmpty()) {
                    body.put("media", JSONArray(media.map {
                        JSONObject().put("token", it.token).put("alt", it.alt) }))
                    if (composeSensitive) body.put("sensitive", true)
                } else if (pollOn) {
                    val opts = pollOptions.map { it.trim() }.filter { it.isNotBlank() }
                    if (opts.size >= 2) body.put("poll", JSONObject().put("options", JSONArray(opts))
                        .put("expires_in", pollExpires).put("multiple", pollMultiple))
                }
                if (altOk) body.put("alt_ok", true)
                composeFrom?.let { body.put("account", it) }
            }
            val got = Core.post(body)
            sending = false
            Core.failed(got)?.let { message = it; return@launch }
            got.optJSONObject("ask_alt")?.let { a ->
                asking = Asking.Confirm(str(a, "text"), { send(altOk = true) }, str(a, "title"),
                    str(a, "send"), str(a, "describe"))
                return@launch
            }
            str(got, "message").takeIf { it.isNotBlank() }?.let { message = it }
            if (got.optBoolean("edited")) {
                message = getApplication<Application>().getString(R.string.edited_done)
            }
            clearEditor()
            places = places.dropLast(1)
            (place as? Place.Thread)?.let {
                reloadThread(it.focus)
                // back in the thread: on what was just written, not at its top
                threadAimAt = got.optString("id").ifBlank { null } ?: p.replyTo?.sid
                threadOpening += 1
            }
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

    // ---- the self-check (dev builds): this phone, this account, read-only ---------------
    data class Check(val name: String, val ok: Boolean?, val ms: Int, val detail: String)

    var checks by mutableStateOf(listOf<Check>())
    var checking by mutableStateOf(false)

    fun openSelfCheck() {
        places = places + Place.SelfCheck
    }

    fun runSelfCheck() {
        if (checking) return
        checking = true
        viewModelScope.launch {
            val names = Core.selfcheckSteps()
            checks = (0 until names.length()).map { Check(names.getString(it), null, 0, "") }
            for (i in checks.indices) {
                val r = Core.selfcheckStep(checks[i].name)
                checks = checks.toMutableList().also {
                    it[i] = Check(r.optString("name"), r.optBoolean("ok"), r.optInt("ms"),
                        r.optString("detail"))
                }
            }
            checking = false
        }
    }

    /** The report (the desktop's bug report + the steps) → its file, to hand over. */
    fun selfCheckReport(device: JSONObject, share: (String) -> Unit) {
        viewModelScope.launch {
            val results = JSONArray()
            checks.forEach {
                results.put(JSONObject().put("name", it.name).put("ok", it.ok == true)
                    .put("ms", it.ms).put("detail", it.detail))
            }
            val got = Core.selfcheckReport(results, device)
            Core.failed(got)?.let { message = it; return@launch }
            share(got.optString("path"))
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
                val ch = o.optJSONArray("choices") ?: JSONArray()
                Setting(o.optString("section"), o.optString("key"), o.optString("kind"),
                    o.optString("title"), o.optString("about"),
                    jsonText(o.opt("value")), jsonText(o.opt("default")),
                    (0 until ch.length()).map { k ->
                        val pair = ch.getJSONArray(k)
                        jsonText(pair.opt(0)) to pair.optString(1)
                    },
                    o.optBoolean("changed"), o.optString("group"))
            })
        }
    }

    /** One option into the file (checked there first); the page shows what it is now. */
    fun setSetting(opt: Setting, json: String) {
        viewModelScope.launch {
            val got = Core.settingSet(opt.section, opt.key, json)
            Core.failed(got)?.let { message = it; return@launch }
            val now = jsonText(got.opt("value"))
            val changed = got.optBoolean("changed")
            settings = settings.map { c ->
                c.copy(options = c.options.map {
                    if (it.section == opt.section && it.key == opt.key)
                        it.copy(value = now, changed = changed) else it
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
        editorFacts = null
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


    // ---- every place of the windows' ≡ menu, profiles, the ⋯ menu: the core's answers ----
    /** Opens links in the browser (the activity sets it: App()). */
    var browse: (String) -> Unit = {}
    var asking by mutableStateOf<Asking?>(null)
    var placeMenu by mutableStateOf(listOf<Pair<String, String>>())
    val pages = mutableStateMapOf<Place.Page, PageView>()
    val profiles = mutableStateMapOf<Place.Profile, ProfileView>()

    private fun push(p: Place) {
        places = places + p
    }

    fun openPlacesMenu() {
        if (place != Place.Menu) push(Place.Menu)
        viewModelScope.launch {
            val arr = Core.places()
            placeMenu = (0 until arr.length()).map {
                val o = arr.getJSONObject(it)
                o.optString("name") to o.optString("title")
            }
        }
    }

    /** A place: pushed over what is open (a tab or the next rows of the same place: in its stead). */
    fun openPage(name: String, arg: String = "", tab: String = "", cursor: String = "") {
        val top = place
        if (top is Place.Page && top.name == name && top.arg == arg && cursor.isNotBlank()) {
            moreRows(top, tab, cursor)
            return
        }
        val p = Place.Page(name, arg, tab)
        places = if (top is Place.Page && top.name == name && top.arg == arg) places.dropLast(1) + p
                 else places + p
        viewModelScope.launch { loadPage(p) }
    }

    private suspend fun loadPage(p: Place.Page) {
        val got = Core.page(p.name, p.arg, p.tab, p.cursor)
        Core.failed(got)?.let { message = it; if (place == p && pages[p] == null) back(); return }
        pages[p] = parsePageView(got)
    }

    /** "More": the place's next rows, under those shown. */
    private fun moreRows(p: Place.Page, tab: String, cursor: String) {
        viewModelScope.launch {
            val got = Core.page(p.name, p.arg, tab.ifBlank { p.tab }, cursor)
            Core.failed(got)?.let { message = it; return@launch }
            val next = parsePageView(got)
            val now = pages[p]
            pages[p] = if (now == null) next else now.copy(rows = now.rows + next.rows, more = next.more)
        }
    }

    /** ⟳ over a thread, a place, a profile: a round at the server, and this asked anew —
     *  the list keeps its place (by its items' keys), whatever comes. */
    fun refreshTop() {
        viewModelScope.launch { Core.refresh() }
        reloadTop()
    }

    fun reloadTop() {
        when (val p = place) {
            is Place.Page -> viewModelScope.launch { loadPage(p) }
            is Place.Profile -> viewModelScope.launch { loadProfile(p) }
            is Place.Thread -> viewModelScope.launch { reloadThread(p.focus) }
            else -> {}
        }
    }

    /** A place's button with its form's values; what it says to do then — done (handle()). */
    fun pageAct(b: PlaceButton, values: JSONObject?, confirmed: Boolean = false, answer: String? = null) {
        viewModelScope.launch {
            val got = Core.placeAct(b.act, confirmed, values, answer)
            got.optJSONObject("page")?.let { placePage = parsePlace(it) }
            handle(got) { c, _, a -> pageAct(b, values, c || confirmed, a ?: answer) }
            loadHub()
        }
    }

    fun openProfile(id: String, show: String? = null) {
        if (id.isBlank()) return
        val p = Place.Profile(id, show)
        val top = place
        places = if (top is Place.Profile && top.id == id) places.dropLast(1) + p else places + p
        viewModelScope.launch { loadProfile(p) }
    }

    private suspend fun loadProfile(p: Place.Profile) {
        val got = Core.account(p.id, p.show)
        Core.failed(got)?.let { message = it; if (place == p && profiles[p] == null) back(); return }
        profiles[p] = parseProfile(got)
    }

    fun profileAct(id: String, key: String, answer: String? = null, confirmed: Boolean = false,
                   chosen: JSONObject? = null) {
        viewModelScope.launch {
            val got = Core.profileAct(id, key, answer, confirmed, chosen)
            handle(got) { c, ch, a -> profileAct(id, key, a ?: answer, c || confirmed, ch ?: chosen) }
        }
    }

    /** A card's ⋯ as the windows have it (common/actions.menu). */
    suspend fun postMenu(p: PostItem): JSONObject = Core.postMenu(p.sid)

    /** A fedtail: link of the ⋯ menu (edit, delete, mute, report…), done the windows' way. */
    fun runLink(url: String, confirmed: Boolean = false, chosen: JSONObject? = null) {
        viewModelScope.launch {
            val got = Core.link(url, confirmed, chosen)
            handle(got) { c, ch, _ -> runLink(url, c || confirmed, ch ?: chosen) }
        }
    }

    /** What the core said to do: ask first (and run again with the answer), open, write, copy. */
    private suspend fun handle(got: JSONObject, again: (Boolean, JSONObject?, String?) -> Unit) {
        Core.failed(got)?.let { message = it; return }
        got.optString("confirm").takeIf { it.isNotBlank() }?.let {
            asking = Asking.Confirm(it, { again(true, null, null) })
            return
        }
        got.optJSONObject("choose")?.let { c ->
            val opts = c.optJSONArray("options") ?: JSONArray()
            asking = Asking.Choose(str(c, "title"), str(c, "text"),
                (0 until opts.length()).map { i ->
                    val o = opts.getJSONObject(i)
                    jsonText(o.opt("key")) to o.optString("label")
                }, str(c, "check")) { key, ticked ->
                again(false, JSONObject().put("key", JSONObject("{\"k\":$key}").opt("k"))
                    .put("ticked", ticked), null)
            }
            return
        }
        got.optJSONObject("ask")?.let { a ->
            asking = Asking.Text(str(a, "title"), str(a, "question"), str(a, "text")) {
                again(false, null, it)
            }
            return
        }
        if (got.optBoolean("reload")) {
            got.optString("message").takeIf { it.isNotBlank() }?.let { message = it }
            restartScreens()
            return
        }
        str(got, "copy").takeIf { it.isNotBlank() }?.let { copy(it) }
        str(got, "alias").takeIf { it.isNotBlank() }?.let { putAlias(it) }
        str(got, "read_up_to").takeIf { it.isNotBlank() }?.let { readUpTo(it) }
        str(got, "message").takeIf { it.isNotBlank() }?.let { message = it }
        got.optJSONObject("compose")?.let { composeFrom(it) }
        got.optJSONObject("open")?.let { openThing(it) }
        if (got.optBoolean("refresh")) {
            if (got.optJSONObject("open") == null && got.optJSONObject("compose") == null) reloadTop()
            current?.let { loadLane(it, keep = true) }
        }
    }

    private fun openThing(o: JSONObject) {
        when {
            str(o, "thread").isNotBlank() -> openThread(str(o, "thread"))
            str(o, "account").isNotBlank() -> openProfile(str(o, "account"))
            o.has("page") -> {
                val pg = o.opt("page")
                if (pg is JSONArray) openPage(pg.optString(0), pg.optString(1))
                else openPage(str(o, "page"), str(o, "arg"), str(o, "tab"), str(o, "cursor"))
            }
            str(o, "url").isNotBlank() -> browse(str(o, "url"))
            str(o, "file").isNotBlank() -> openConfig()
            o.optBoolean("back") -> back()
        }
    }

    private fun copy(text: String) {
        val cm = getApplication<Application>().getSystemService(ClipboardManager::class.java)
        cm?.setPrimaryClip(ClipData.newPlainText("fedtail", text))
        message = getApplication<Application>().getString(R.string.copied)
    }

    /** "Read up to here": this post and everything older in the lane. */
    private fun readUpTo(sid: String) {
        val inOrder = if (newestFirst) posts.reversed() else posts
        val i = inOrder.indexOfFirst { it.sid == sid || it.id == sid }
        if (i < 0) return
        markRead(inOrder.take(i + 1).map { it.key })
    }

    /** A poll answered: the card as it is now, wherever it shows. */
    fun vote(p: PostItem, choices: List<Int>) {
        if (choices.isEmpty()) return
        viewModelScope.launch {
            val got = Core.vote(p.sid, choices)
            Core.failed(got)?.let { message = it; return@launch }
            val now = parsePost(got)
            val swap = { x: PostItem ->
                if (x.sid == p.sid) x.copy(poll = now.poll, pollOpen = now.pollOpen) else x
            }
            posts = posts.map(swap)
            threadPosts = threadPosts.map(swap)
            pages.keys.toList().forEach { k ->
                pages[k]?.let { v -> pages[k] = v.copy(rows = v.rows.map { r ->
                    r.post?.let { r.copy(post = swap(it)) } ?: r }) }
            }
            profiles.keys.toList().forEach { k ->
                profiles[k]?.let { v -> profiles[k] = v.copy(posts = v.posts.map(swap)) }
            }
        }
    }

    // ---- the editor: words, a warning, the language, pictures, a poll; an edit, a quote --
    var composeCw by mutableStateOf("")
    var composeCwOn by mutableStateOf(false)
    var composeLang by mutableStateOf("")
    var composeSensitive by mutableStateOf(false)
    var attachments by mutableStateOf(listOf<Attachment>())
    var uploading by mutableStateOf(0)
    var editId by mutableStateOf<String?>(null)
    var quoteId by mutableStateOf<String?>(null)
    var quoteOf by mutableStateOf("")
    var pollOn by mutableStateOf(false)
    var pollOptions by mutableStateOf(listOf("", ""))
    var pollMultiple by mutableStateOf(false)
    var pollExpires by mutableStateOf(86400)
    var editorFacts by mutableStateOf<JSONObject?>(null)
    var composeFrom by mutableStateOf<String?>(null) // all accounts in one: whose post

    /** Whom a post may go from (all accounts in one window): (key, "from @x@server"). */
    fun fromAccounts(): List<Pair<String, String>> {
        val arr = editorFacts?.optJSONArray("accounts") ?: return emptyList()
        return (0 until arr.length()).map { arr.getJSONArray(it) }.map { it.optString(0) to it.optString(1) }
    }

    private fun clearEditor() {
        composeText = ""
        composeCw = ""
        composeCwOn = false
        composeLang = editorFacts?.optString("language") ?: ""
        composeSensitive = false
        attachments = emptyList()
        editId = null
        quoteId = null
        quoteOf = ""
        pollOn = false
        pollOptions = listOf("", "")
        pollMultiple = false
        pollExpires = 86400
        composeFrom = null
    }

    private fun loadEditorFacts() {
        if (editorFacts != null) return
        viewModelScope.launch {
            val got = Core.editor()
            if (Core.failed(got) == null) {
                editorFacts = got
                if (composeLang.isBlank()) composeLang = got.optString("language")
            }
        }
    }

    /** The languages to pick from: (code, words), "" — the default. */
    fun languages(): List<Pair<String, String>> {
        val arr = editorFacts?.optJSONArray("languages") ?: return emptyList()
        return (0 until arr.length()).map { arr.getJSONArray(it) }
            .map { it.optString(0) to it.optString(1) }
            .filter { !it.first.startsWith("\u0000") } // "another language…": not here yet
    }

    fun pollLengths(): List<Pair<Int, String>> {
        val arr = editorFacts?.optJSONArray("poll_lengths") ?: return emptyList()
        return (0 until arr.length()).map { arr.getJSONArray(it) }.map { it.optInt(0) to it.optString(1) }
    }

    fun maxMedia(): Int = editorFacts?.optInt("max_media", 4) ?: 4
    fun maxOptions(): Int = editorFacts?.optInt("max_options", 4) ?: 4
    fun charLimit(): Int = editorFacts?.optInt("limit", 500) ?: 500

    /** The editor as a link asked: my post to correct, a quote, a reply, a redraft. */
    private fun composeFrom(c: JSONObject) {
        val parentId = str(c, "reply_to")
        val parent = if (parentId.isBlank()) null else (posts + threadPosts)
            .firstOrNull { it.sid == parentId || it.id == parentId }
        compose(parent)
        if (parent == null && parentId.isNotBlank()) replyToId = parentId
        str(c, "text").takeIf { it.isNotBlank() }?.let { composeText = it }
        str(c, "cw").takeIf { it.isNotBlank() }?.let { composeCw = it; composeCwOn = true }
        str(c, "visibility").takeIf { it.isNotBlank() }?.let {
            composeVisibility = if (it == "private") "followers" else it
        }
        str(c, "lang").takeIf { it.isNotBlank() }?.let { composeLang = it }
        editId = str(c, "edit").ifBlank { null }
        quoteId = str(c, "quote").ifBlank { null }
        quoteOf = str(c, "quote_of")
        val media = c.optJSONArray("media")
        if (media != null) {
            attachments = (0 until media.length()).map { media.getJSONObject(it) }.map {
                Attachment("", "", str(it, "kind"), str(it, "alt"), str(it, "id"), str(it, "url"))
            }
        }
    }

    /** A reply whose parent isn't on screen (a redraft): only its id. */
    private var replyToId: String? = null

    /** A file the phone picked, copied into the cache and handed to the core:
     *  → (token, kind: image | video | audio), or null (said why). */
    private suspend fun handOver(uri: Uri): Pair<String, String>? {
        val app = getApplication<Application>()
        return try {
            val type = app.contentResolver.getType(uri) ?: ""
            val ext = MimeTypeMap.getSingleton().getExtensionFromMimeType(type) ?: "bin"
            val name = "upload-${System.nanoTime()}.$ext"
            val file = File(app.cacheDir, name)
            withContext(Dispatchers.IO) {
                val inp = app.contentResolver.openInputStream(uri) ?: error("unreadable")
                inp.use { i -> file.outputStream().use { i.copyTo(it) } }
            }
            val got = Core.upload(file.absolutePath, name)
            Core.failed(got)?.let { message = it; return null }
            got.optString("token") to when {
                type.startsWith("video/") -> "video"
                type.startsWith("audio/") -> "audio"
                else -> "image"
            }
        } catch (e: Exception) {
            message = e.message ?: e.toString()
            null
        }
    }

    /** Pictures or videos for the post being written. */
    fun attach(uris: List<Uri>) {
        val app = getApplication<Application>()
        val room = maxMedia() - attachments.size
        if (room <= 0) {
            message = app.getString(R.string.media_full, maxMedia())
            return
        }
        uris.take(room).forEach { uri ->
            uploading += 1
            viewModelScope.launch {
                handOver(uri)?.let { (token, kind) ->
                    attachments = attachments + Attachment(token, token, kind, preview = uri.toString())
                }
                uploading -= 1
            }
        }
    }

    /** A place's file field (a new avatar, a header): the token for its form. */
    fun uploadFor(uri: Uri, done: (String) -> Unit) {
        viewModelScope.launch { handOver(uri)?.let { done(it.first) } }
    }

    /** ⋯ → reply with a quote: the post's words, each line after "> ". */
    fun quoteReply(p: PostItem) {
        compose(p)
        val quoted = p.text.trim().lines().joinToString("\n") { "> $it" }
        composeText = composeText + "\n" + quoted + "\n\n"
    }

    fun detach(a: Attachment) {
        attachments = attachments - a
    }

    fun describe(a: Attachment, alt: String) {
        attachments = attachments.map { if (it.token == a.token && it.id == a.id) it.copy(alt = alt) else it }
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

    /** A place's button: a thread opens here; the rest the core does (and may ask first). */
    fun placeAct(b: PlaceButton, confirmed: Boolean = false) {
        placeConfirm = null
        if (b.act.size == 3 && b.act[0] == "post" && b.act[1] == "thread") {
            openThread(b.act[2])
            return
        }
        pageAct(b, null, confirmed, null)
    }

    private fun parseButton(o: JSONObject?): PlaceButton? = o?.let { b ->
        val act = b.optJSONArray("act") ?: JSONArray()
        PlaceButton(b.optString("label"), List(act.length()) { act.optString(it) },
            b.optBoolean("primary"), b.optString("tip"))
    }

    private fun parsePlace(o: JSONObject): PlacePage {
        val arr = o.optJSONArray("rows") ?: JSONArray()
        val rows = List(arr.length()) { i ->
            val r = arr.getJSONObject(i)
            val bs = r.optJSONArray("buttons") ?: JSONArray()
            val title = r.optString("title")
            PlaceRow(title.removePrefix("● "), r.optString("line"), r.optString("key"),
                (0 until bs.length()).mapNotNull { parseButton(bs.optJSONObject(it)) },
                fresh = title.startsWith("● "))
        }
        return PlacePage(rows, o.optString("empty"), parseButton(o.optJSONObject("submit")),
            parseButton(o.optJSONObject("more")))
    }


    private fun parseAccount(o: JSONObject?) = AccountItem(str(o, "id"), str(o, "handle"),
        str(o, "name").ifBlank { str(o, "handle") }, str(o, "avatar"))

    private fun parsePageView(o: JSONObject): PageView {
        val rows = o.optJSONArray("rows") ?: JSONArray()
        val form = o.optJSONArray("form") ?: JSONArray()
        val tabs = o.optJSONArray("tabs") ?: JSONArray()
        return PageView(
            name = str(o, "name"), title = str(o, "title"), arg = str(o, "arg"), hint = str(o, "hint"),
            tabs = (0 until tabs.length()).map { tabs.getJSONArray(it) }
                .map { it.optString(0) to it.optString(1) },
            tab = str(o, "tab"),
            rows = (0 until rows.length()).map { rows.getJSONObject(it) }.map { r ->
                val bs = r.optJSONArray("buttons") ?: JSONArray()
                PageRow(str(r, "kind"), str(r, "title"), str(r, "line"), str(r, "key"),
                    (0 until bs.length()).mapNotNull { parseButton(bs.optJSONObject(it)) },
                    r.optJSONObject("post")?.let { parsePost(it) },
                    r.optJSONObject("account")?.let { parseAccount(it) }, str(r, "html"))
            },
            form = (0 until form.length()).map { form.getJSONObject(it) }.map { f ->
                val ch = f.optJSONArray("choices") ?: JSONArray()
                PageField(str(f, "name"), str(f, "label"), f.optString("kind", "line"),
                    if (f.isNull("value")) null else f.opt("value"),
                    (0 until ch.length()).map { ch.getJSONArray(it) }
                        .map { it.optString(0) to it.optString(1) }, str(f, "tip"))
            },
            submit = parseButton(o.optJSONObject("submit")), more = parseButton(o.optJSONObject("more")),
            empty = str(o, "empty"))
    }

    private fun parseProfile(o: JSONObject): ProfileView {
        val acc = o.optJSONObject("account") ?: JSONObject()
        val fields = acc.optJSONArray("fields") ?: JSONArray()
        val meta = o.optJSONArray("meta") ?: JSONArray()
        val acts = o.optJSONArray("actions") ?: JSONArray()
        val shows = o.optJSONArray("shows") ?: JSONArray()
        return ProfileView(
            account = parseAccount(acc), note = str(acc, "note"), header = str(acc, "header"),
            counts = str(acc, "counts"),
            fields = (0 until fields.length()).map { fields.getJSONObject(it) }
                .map { Triple(str(it, "name"), str(it, "value"), it.optBoolean("verified")) },
            own = acc.optBoolean("own"),
            meta = (0 until meta.length()).map { meta.optString(it) },
            noteLine = str(o, "note_line"),
            actions = (0 until acts.length()).map { acts.getJSONObject(it) }
                .map { ProfileButton(str(it, "key"), str(it, "label"), str(it, "tip"), it.optBoolean("primary")) },
            shows = (0 until shows.length()).map { shows.getJSONObject(it) }
                .map { Triple(str(it, "key"), str(it, "label"), it.optBoolean("on")) },
            showTip = str(o, "show_tip"),
            posts = parsePosts(o.optJSONArray("posts")),
            pinned = (o.optJSONArray("posts") ?: JSONArray()).let { a ->
                (0 until a.length()).map { a.getJSONObject(it) }.filter { it.optBoolean("pinned") }
                    .map { it.optString("item", it.optString("id")) }.toSet()
            },
            featured = (o.optJSONArray("featured") ?: JSONArray()).let { a ->
                (0 until a.length()).map { a.getJSONObject(it) }.map { f ->
                    val tags = f.optJSONArray("tags") ?: JSONArray()
                    val people = f.optJSONArray("people") ?: JSONArray()
                    FeaturedLine(str(f, "title"), str(f, "text"),
                        (0 until tags.length()).map { tags.optString(it) },
                        (0 until people.length()).map { parseAccount(people.getJSONObject(it)) })
                }
            },
            familiar = str(o, "familiar"),
            moved = o.optJSONObject("moved")?.let { m ->
                str(m, "text") to parseAccount(m.optJSONObject("account")) },
            movedOpen = o.optJSONObject("moved")?.let { str(it, "open") } ?: "",
            older = parseOlder(o.optJSONObject("older")),
            maxId = str(o, "max_id"))
    }

    private fun parseOlder(o: JSONObject?) = o?.let { OlderOffer(str(it, "label"), str(it, "cursor")) }

    /** "More" under a profile: the next posts, mine first, then from their own server. */
    fun profileMore(p: Place.Profile) {
        val v = profiles[p] ?: return
        val offer = v.older ?: return
        if (v.loadingMore) return
        profiles[p] = v.copy(loadingMore = true)
        viewModelScope.launch {
            val got = Core.accountMore(p.id, p.show, v.maxId, offer.cursor)
            val now = profiles[p] ?: return@launch
            if (Core.failed(got) != null) {
                message = Core.failed(got)
                profiles[p] = now.copy(loadingMore = false)
                return@launch
            }
            val have = now.posts.map { it.key }.toSet()
            profiles[p] = now.copy(
                posts = now.posts + parsePosts(got.optJSONArray("posts")).filter { it.key !in have },
                maxId = str(got, "max_id").ifBlank { now.maxId },
                older = parseOlder(got.optJSONObject("older")), loadingMore = false)
        }
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
            accountId = str(acc, "id"),
            pollOptions = poll?.optJSONArray("options")?.let { a ->
                (0 until a.length()).map { str(a.getJSONObject(it), "title") } } ?: emptyList(),
            pollMultiple = poll?.optBoolean("multiple") ?: false,
            pollOpen = poll != null && !poll.optBoolean("voted") && !poll.optBoolean("expired") &&
                !o.optBoolean("own"),
            own = o.optBoolean("own"),
            edited = o.optBoolean("edited"),
            quoteId = str(o.optJSONObject("quote"), "id"),
            quoteWho = o.optJSONObject("quote")?.optJSONObject("account")?.let { a ->
                str(a, "name").ifBlank { str(a, "handle") } } ?: "",
            quoteText = o.optJSONObject("quote")?.let { q ->
                str(q, "text").ifBlank { str(q, "note") } } ?: "",
        )
    }
}
