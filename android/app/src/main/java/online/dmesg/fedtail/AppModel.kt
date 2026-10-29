package online.dmesg.fedtail

import android.app.Application
import android.content.ClipData
import android.content.ClipboardManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
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

/** What stands over the lanes: a thread, the editor, pictures, the config. Back closes it. */
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
    val fresh: Int = 0, // of them, what the last update brought ("of them new 56")
    val pos: Int = 0, // where the set (lanes.preset) puts it: the sidebar's order
    val group: String = "", // the set's section it stands under ("Timelines", "Personal"…)
) {
    /** The count as shown: "300+" when there may be more than the lane holds. */
    val count: String get() = if (capped) "$unread+" else "$unread"
}

/** One of the server's announcements for the strip (bridge.announcements). */
data class Announce(
    val id: String, val head: String, val text: String,
    val reactions: List<Triple<String, Int, Boolean>>, // (emoji, count, mine)
)

/** kind: you | reading | lists | browse (bridge.hub) */
data class HubSection(val kind: String, val lanes: List<HubLane>)

data class MediaItem(
    val kind: String, val preview: String, val url: String, val alt: String,
    val w: Int, val h: Int,
)

/** A button of a place (common/places.py Btn): act = [place, key, data]. */
data class PlaceButton(val label: String, val act: List<String>, val primary: Boolean, val tip: String)

/** An event's row in any lane that takes events (common/activity.EventParts, web lane
 *  "events": the windows' row): every action is a fedtail: link, done as a card's links. */
data class EventItem(
    val kind: String,
    val people: List<Pair<String, String>>,   // (name, fedtail:account/<id>)
    val more: String,                         // "and 5 more"
    val what: String, val whenText: String,
    val notice: String,                       // the server's own notice, or ""
    val post: String, val postLink: String,   // «the post it is about», fedtail:thread/<id>
    val hide: String, val hideTip: String,    // × — fedtail:eventhide/<ids>
    val answers: List<Pair<String, String>>,  // a request's (yes link, no link)
    val answerWords: List<Pair<String, String>>, // (words, tip) of yes, of no
    val tip: String,
)

data class LinkCard(
    val url: String, val title: String, val provider: String, val image: String,
    val description: String = "",
)

data class PostItem(
    val key: String, val id: String, val sid: String, val alias: String, val name: String,
    // where its thread opens: "post" / "first_unread" (CardSpec.open_at)
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
    val pollShares: List<Int> = emptyList(),     // each option's share, % (results as bars)
    val pollMine: Set<Int> = emptySet(),         // the options I voted for
    val pollSummary: String = "",                // how many people, until when
    val own: Boolean = false,
    val edited: Boolean = false,
    val quoteId: String = "",        // the post it quotes, or a note why it can't be shown
    val quoteWho: String = "",
    val quoteText: String = "",
    val nameHtml: String = "",       // the name with its :emoji: as pictures (if any)
    val openAt: String = "post",
    val nameColor: String = "",      // people.nick_colors: my colour for their name
    val labels: String = "",         // the windows' marks: "old, 40 days", "bot", edited…
    val reactions: String = "",      // "👍 3 :blobcat: 2"
    val via: String = "",            // all accounts in one: which of mine got it
    val viaColor: String = "",       // …in that account's colour (ui.account_colors)
    // the windows' lines around a card (common/cardtext.py), each (words, fedtail: link):
    val newcomer: Pair<String, String>? = null,     // "👤 New in this private talk: @eve"
    val threadNews: Pair<String, String>? = null,   // "🔔 3 new in the thread"
    val myReplies: List<Pair<String, String>> = emptyList(),  // "↳ you replied …"
    val visibility: String = "",     // public | unlisted | private | direct
    val meta: List<Pair<String, String>> = emptyList(),  // the marks with their links (time, edits)
    val foldedBy: String = "",       // "Folded by the filter «x»": a server filter's "warn"
    val quoteLine: Pair<String, String>? = null,  // the quote as one line; null — none shown
    val conversation: Pair<String, String>? = null,  // "💬 N in the conversation, new: M…"
    val boosted: Pair<String, String>? = null,  // "♻ boosted by X · 14:02" → their profile
    val contextLine: Pair<String, String>? = null,  // the parent's line when it isn't here yet
    val quoteOff: Boolean = false,   // the card's words leave the quote out (feed.quotes = "off")
    // not a post but an event's row of the lane (likes, follows, a follow request…): its
    // key "event:<id>" — seen on screen as a post is (Core.read)
    val event: EventItem? = null,
)

/** A lane's switches from its header (common/lane.py, the windows' and the page's). */
data class LaneSwitches(
    val info: String,                                   // why it is empty / what it holds
    val filters: List<Triple<String, String, String>>,  // (key, words, tip)
    val filter: String,
    val convOffered: Boolean, val convOn: Boolean, val convWords: List<String>,
    val mediaActive: Boolean, val mediaLabel: String, val mediaAll: String,
    val media: List<Triple<String, String, Boolean>>,   // (kind, words, on)
    val clear: Pair<String, String>? = null,            // a lane of events only: (words, tip)
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
                     val choices: List<Pair<String, String>>, val tip: String,
                     val scan: Boolean = false) // a QR code may fill it: "Scan" beside it

/** A place's row: kind item | post | account | tag | text | heading | html; qr — a QR code's
 *  rows of "1"/"0" (common/qr.rows) to draw, dark on white. */
data class PageRow(val kind: String, val title: String, val line: String, val key: String,
                   val buttons: List<PlaceButton>, val post: PostItem?, val account: AccountItem?,
                   val html: String, val qr: List<String> = emptyList())

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
                      val alt: String = "", val id: String = "", val preview: String = "",
                      val focus: Pair<Float, Float>? = null, // -1…1 each, y up (previews' centre)
                      val cover: String = "",                 // a video's or sound's picture (token)
                      val coverPreview: String = "")

/** What the screens show and what they ask of the core; lives as long as the app's task. */
class AppModel(app: Application) : AndroidViewModel(app) {
    var screen by mutableStateOf<Screen>(Screen.Starting)
    var demo by mutableStateOf(false)
    var handle by mutableStateOf("")
    var newestFirst by mutableStateOf(false)
    var markOnScroll by mutableStateOf(true)
    var defaultVisibility by mutableStateOf("followers")
    var hideSensitive by mutableStateOf(true)
    var prefetch by mutableStateOf("previews") // feed.prefetch: pictures fetched ahead
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
    var hubSlow by mutableStateOf("") // slow mode on: "slow · next at 14:30"
    var busy by mutableStateOf(false)  // a poll round on: the empty lane's opossum swings
    var hubWithNews by mutableStateOf(0)
    var hubPinned by mutableStateOf(listOf<String>()) // phone.pinned, as lanes here

    var current by mutableStateOf<String?>(null) // null: the overview of lanes
    var title by mutableStateOf("")
    var posts by mutableStateOf(listOf<PostItem>())
    var divider by mutableStateOf<Pair<String, String>?>(null) // (post key, "new below · N")
    var startKey by mutableStateOf<String?>(null) // the card a lane opened anew stands on
    var opening by mutableStateOf(0) // grows each time a lane opens anew: the list re-aims
    var aimed = 0                     // the opening the list last aimed at
    var refreshing by mutableStateOf(false) // asked by ⟳: a thin bar under the title
    var pulling by mutableStateOf(false)    // asked by pulling the list down
    var message by mutableStateOf<String?>(null)

    var places by mutableStateOf(listOf<Place>())
    val place: Place? get() = places.lastOrNull()

    var threadPosts by mutableStateOf(listOf<PostItem>())
    // the windows' head over a thread: {title, info ("12 answers · #k7q"), via, subscribed,
    // sub, sub_tip} (web/server.py thread_head)
    var threadHead by mutableStateOf<JSONObject?>(null)
    // threads.thread_progress: "⇣ fetching replies: 3 of 12" — "" when nothing goes on
    var threadProgress by mutableStateOf("")
    private var progressWatch: Job? = null
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


    var loginServer by mutableStateOf("")
    var loginProxyField by mutableStateOf(false)  // net.proxy_at_login
    var loginProxy by mutableStateOf("")
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
            else -> {
                loginProxyField = st.optBoolean("proxy_at_login")
                loginProxy = st.optString("proxy")
                screen = Screen.Login
            }
        }
    }

    // ---- logging in --------------------------------------------------------------------
    fun beginLogin(openBrowser: (String) -> Unit) {
        if (loginBusy || loginServer.isBlank()) return
        loginBusy = true
        viewModelScope.launch {
            val got = Core.loginBegin(loginServer, if (loginProxyField) loginProxy else null)
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

    /** ★ / ♻ / ↩ from another account of the window (the card's ⋯ → "As…"). */
    fun actAs(p: PostItem, tag: String, action: String) {
        message = getApplication<Application>().getString(R.string.act_as_wait)
        viewModelScope.launch {
            val got = Core.actAs(p.sid, tag, action)
            Core.failed(got)?.let { message = it; return@launch }
            got.optJSONObject("post")?.let { compose(parsePost(it)) }
            str(got, "message").takeIf { it.isNotBlank() }?.let { message = it }
        }
    }

    /** ≡ → Try a theme: one of the windows' themes for this run; the config keeps its own. */
    fun tryTheme() {
        viewModelScope.launch {
            val got = Core.themes()
            Core.failed(got)?.let { message = it; return@launch }
            val list = got.optJSONArray("themes") ?: JSONArray()
            asking = Asking.Choose(str(got, "title"), str(got, "tip"),
                (0 until list.length()).map { list.getJSONObject(it) }.map { t ->
                    str(t, "name") to ((if (t.optBoolean("on")) "● " else "") + str(t, "label"))
                }, "") { name, _ ->
                viewModelScope.launch {
                    val r = Core.tryTheme(name)
                    Core.failed(r)?.let { message = it; return@launch }
                    loadTheme()
                    str(r, "message").takeIf { it.isNotBlank() }?.let { message = it }
                }
            }
        }
    }

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
        prefetch = me.optString("prefetch", "previews")
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
            ?: lanes.firstOrNull()?.name  // the core says which (ui.start_lane)
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
        sharedOnStart?.let { openShared(it, sharedBrowser) }
        sharedOnStart = null
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
                    l.optString("peek"), l.optBoolean("capped"), l.optInt("fresh"),
                    l.optInt("pos"), l.optString("group"))
            })
        }
        val order = got.optJSONArray("order") ?: JSONArray()
        hubOrder = (0 until order.length()).map { order.getString(it) }
        val pin = got.optJSONArray("pinned") ?: JSONArray()
        hubPinned = (0 until pin.length()).map { pin.getString(it) }
        hubUnread = got.optInt("unread")
        hubWithNews = got.optInt("with_news")
        hubSlow = got.optString("slow")
    }

    /** The tiles: phone.pinned in its order, or (none pinned) every lane with a count;
     *  each with "is it yours" (tinted when there's news). */
    fun tileLanes(): List<Pair<HubLane, Boolean>> {
        val all = hub.flatMap { s -> s.lanes.map { it to (s.kind == "you") } }
        if (hubPinned.isEmpty()) return all.filter { (l, _) -> hub.any { s -> s.kind != "browse" && l in s.lanes } }
            .sortedBy { it.first.pos }
        return hubPinned.mapNotNull { name -> all.firstOrNull { it.first.name == name } }
    }

    /** Under the tiles, as rows: (lane, only browsed — no count). */
    fun restLanes(): List<Pair<HubLane, Boolean>> {
        val tiles = tileLanes().map { it.first.name }.toSet()
        return hub.flatMap { s -> s.lanes.map { it to (s.kind == "browse") } }
            .filter { it.first.name !in tiles }
            .sortedBy { it.first.pos } // as the set has them, its sections in their order
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
        laneSwitches = parseSwitches(got)
        var list = withEvents(parsePosts(got.optJSONArray("posts")), got.optJSONArray("events"))
        if (newestFirst) list = list.reversed()
        posts = list
        laneOlder = got.optBoolean("older")
        val div = got.optJSONObject("divider")
        divider = div?.let { d ->
            list.firstOrNull { it.id == d.optString("before") }?.key?.let { it to d.optString("text") }
        }
        // where reading starts, the core's (feed.start_at, "new below"): none — the newest end
        startKey = got.optString("start").takeIf { it.isNotBlank() }
            ?.let { s -> list.firstOrNull { it.id == s }?.key }
        if (!keep) opening += 1
        pendingAim?.let { key -> if (list.any { it.key == key }) { aimKey = key; pendingAim = null } }
    }

    var laneSwitches by mutableStateOf<LaneSwitches?>(null)

    private fun parseSwitches(o: JSONObject): LaneSwitches {
        val fs = o.optJSONArray("filters") ?: JSONArray()
        val conv = o.optJSONObject("conversations") ?: JSONObject()
        val cw = conv.optJSONArray("words") ?: JSONArray()
        val media = o.optJSONObject("media") ?: JSONObject()
        val kinds = media.optJSONArray("kinds") ?: JSONArray()
        return LaneSwitches(str(o, "info"),
            (0 until fs.length()).map { fs.getJSONArray(it) }
                .map { Triple(it.optString(0), it.optString(1), it.optString(2)) },
            str(o, "filter"), conv.optBoolean("offered"), conv.optBoolean("on"),
            (0 until cw.length()).map { cw.optString(it) },
            media.optBoolean("active"), str(media, "label"), str(media, "all"),
            (0 until kinds.length()).map { kinds.getJSONArray(it) }
                .map { Triple(it.optString(0), it.optString(1), it.optBoolean(2)) },
            o.optJSONObject("clear")?.let { str(it, "label") to str(it, "tip") })
    }

    /** "Clear" over a lane of events only: every notification, on the server too (asked first). */
    fun laneClear(confirmed: Boolean = false) {
        val name = current ?: return
        viewModelScope.launch {
            val got = Core.laneClear(name, confirmed)
            Core.failed(got)?.let { message = it; return@launch }
            str(got, "confirm").takeIf { it.isNotBlank() }?.let {
                asking = Asking.Confirm(it, { laneClear(confirmed = true) })
                return@launch
            }
            loadLane(name, keep = true)
            loadHub()
        }
    }

    /** A switch of the lane's header: {filter} | {conversations} | {media, on}. */
    fun laneSet(body: JSONObject) {
        val name = current ?: return
        viewModelScope.launch {
            Core.failed(Core.laneSet(body.put("name", name)))?.let { message = it; return@launch }
            loadLane(name, keep = true)
        }
    }

    // ---- finding: in the lane, deeper, in every lane (common/find.py) -------------------
    var findOpen by mutableStateOf(false)
    var findText by mutableStateOf("")
    var findIds by mutableStateOf(listOf<String>())
    var findAt by mutableStateOf(0)
    var findWords by mutableStateOf("")       // "2 of 5", "nothing"
    var aimKey by mutableStateOf<String?>(null) // the list stands on this post (a match)
    private var pendingAim: String? = null       // …once the lane opened has it

    fun find(step: Int = 0) {
        val name = current ?: return
        val q = findText.trim()
        if (q.isBlank()) return
        viewModelScope.launch {
            if (step == 0) {
                val got = Core.find(name, q)
                Core.failed(got)?.let { message = it; return@launch }
                val ids = got.optJSONArray("ids") ?: JSONArray()
                findIds = (0 until ids.length()).map { ids.optString(it) }
                findAt = 0
                findWords = str(got, "text")
            } else if (findIds.isNotEmpty()) {
                findAt = Math.floorMod(findAt + step, findIds.size)
                findWords = "${findAt + 1} / ${findIds.size}"
            }
            findIds.getOrNull(findAt)?.let { id ->
                posts.firstOrNull { it.id == id || it.sid == id }?.let { aimKey = it.key }
            }
        }
    }

    /** "Deeper": the lane grows down to an older match. */
    fun findDeeper() {
        val name = current ?: return
        viewModelScope.launch {
            val got = Core.findDeeper(name, findText.trim())
            Core.failed(got)?.let { message = it; return@launch }
            str(got, "text").takeIf { it.isNotBlank() }?.let { findWords = it }
            loadLane(name, keep = true)
            find()
        }
    }

    /** "In every lane": the matches, lane by lane; one picked — its lane, standing on it. */
    fun findEverywhere() {
        val q = findText.trim()
        if (q.isBlank()) return
        viewModelScope.launch {
            val got = Core.findEverywhere(q)
            Core.failed(got)?.let { message = it; return@launch }
            val hits = got.optJSONArray("hits") ?: JSONArray()
            if (hits.length() == 0) { message = str(got, "text"); return@launch }
            asking = Asking.Choose(str(got, "text"), "", (0 until hits.length()).map { i ->
                val h = hits.getJSONObject(i)
                i.toString() to str(h, "title")
            }.distinctBy { it.second }.let { firsts ->
                // one row a lane: its first match (the list says how many all in all)
                firsts
            }, "") { pick, _ ->
                val h = hits.getJSONObject(pick.toInt())
                pendingAim = str(h, "item").ifBlank { str(h, "id") }
                viewModelScope.launch {
                    // further back than the lane shows: it grows down to the match first
                    Core.reveal(str(h, "lane"), h.optInt("index"))
                    showLane(str(h, "lane"))
                }
            }
        }
    }

    fun pollRefresh(p: PostItem) {
        viewModelScope.launch {
            val got = Core.pollRefresh(p.sid)
            Core.failed(got)?.let { message = it; return@launch }
            val now = parsePost(got)
            val swap = { x: PostItem ->
                if (x.sid == p.sid) x.copy(poll = now.poll, pollOpen = now.pollOpen,
                    pollOptions = now.pollOptions) else x
            }
            posts = posts.map(swap)
            threadPosts = threadPosts.map(swap)
        }
    }

    var threadCwOpen by mutableStateOf(false) // ⚠ over a thread: every warning open

    var laneOlder by mutableStateOf(false)   // "earlier" can bring older posts
    var loadingOlder by mutableStateOf(false)

    /** "Earlier" at the lane's top: older posts from the server (history counts as read). */
    /** "Earlier": older posts from the server. ahead: the button came in sight
     *  (reading.older_ahead) — the core decides whether to ask (core.older_ahead). */
    fun loadOlder(ahead: Boolean = false) {
        val name = current ?: return
        if (loadingOlder) return
        loadingOlder = true
        viewModelScope.launch {
            val got = Core.older(name, ahead)
            if (ahead && !got.optBoolean("asked", true)) { loadingOlder = false; return@launch }
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
            // the bar is the round's: it goes when the round is over, news or none (it
            // waited for news, and a round bringing nothing kept it 8 s, the lane pushed
            // down by it); the news themselves come through watch()
            val began = System.currentTimeMillis()
            var seenBusy = false
            while (System.currentTimeMillis() - began < 8000) {
                delay(250)
                val st = Core.status()
                val on = Core.failed(st) == null && st.optBoolean("busy")
                seenBusy = seenBusy || on
                val waited = System.currentTimeMillis() - began
                if (!on && (seenBusy || waited >= if (pulled) 1500 else 1000)) break
            }
            pulling = false
            refreshing = false
        }
    }

    /** "Mark all read", as the windows' button: the whole lane in the core, not only
     *  the posts loaded here; the overview's counts follow. */
    fun markLaneRead() {
        val name = current ?: return
        posts = posts.map { if (it.unread) it.copy(unread = false) else it }
        viewModelScope.launch {
            Core.laneRead(name)
            loadHub()
        }
    }

    private var stoodKey: String? = null

    /** The card on top of the screen, the scroll standing: where the lane opens next
     *  time, on the phone or anywhere else (LaneModel.stood). */
    fun stood(key: String) {
        val lane = current ?: return
        if (key == stoodKey || posts.none { it.key == key }) return
        stoodKey = key
        viewModelScope.launch { Core.stood(lane, key) }
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

    private var threadSeq = 0 // the core's "a thread grew" count, as last seen

    // ---- the server's announcements (ui.announcements = "banner"): the windows' strip --------
    var announces by mutableStateOf(listOf<Announce>())
    var announceOk by mutableStateOf("")
    private var announcedAt = 0L

    /** Asked at the start and twice an hour (admins post rarely), as the windows do. */
    private suspend fun checkAnnouncements(force: Boolean = false) {
        val now = System.currentTimeMillis()
        if (!force && now - announcedAt < 30 * 60 * 1000L) return
        announcedAt = now
        val got = Core.announcements()
        if (Core.failed(got) != null) return
        announceOk = got.optString("ok")
        val arr = got.optJSONArray("items") ?: JSONArray()
        announces = (0 until arr.length()).map { i ->
            val a = arr.getJSONObject(i)
            val rs = a.optJSONArray("reactions") ?: JSONArray()
            Announce(a.optString("id"), a.optString("head"), a.optString("text"),
                (0 until rs.length()).map { j ->
                    val r = rs.getJSONObject(j)
                    Triple(r.optString("name"), r.optInt("count"), r.optBoolean("me"))
                })
        }
    }

    /** "Got it": the server remembers it, the next one shows. */
    fun dismissAnnouncement() {
        val a = announces.firstOrNull() ?: return
        announces = announces.drop(1)
        viewModelScope.launch {
            Core.failed(Core.announcementDismiss(a.id))?.let { message = it }
        }
    }

    /** A reaction on or off — counted at once, as the server will count it. */
    fun reactAnnouncement(a: Announce, name: String) {
        val mine = a.reactions.firstOrNull { it.first == name }?.third ?: false
        val on = !mine
        val rs = a.reactions.map {
            if (it.first == name) Triple(name, maxOf(0, it.second + if (on) 1 else -1), on) else it
        }
        announces = announces.map { if (it.id == a.id) it.copy(reactions = rs) else it }
        viewModelScope.launch {
            Core.failed(Core.announcementReact(a.id, name, on))?.let { message = it }
        }
    }

    /** While on screen: whatever the core learns (a poll, sync) reloads what is shown. */
    private fun watch() {
        if (watcher?.isActive == true) return
        watcher = viewModelScope.launch {
            while (isActive) {
                checkAnnouncements()
                val v = Core.waitChange(version, 25)
                // a poll round began or ended: "updating…" / "updated at" on the overview,
                // so a lane with nothing new doesn't look like a dead network
                val st = Core.status()
                if (Core.failed(st) == null) {
                    hubSlow = st.optString("text")
                    busy = st.optBoolean("busy")
                }
                val grew = st.optInt("threads")
                if (v != version) {
                    version = v
                    // the windows' notes into the shade (notify.when_focused: even now)
                    Notifier.take(getApplication(), Core.notes(Notifier.lastSeq))
                    lanes = parseLanes(Core.lanes())
                    loadHub()
                    current?.let { loadLane(it, keep = true) }
                    // an open thread grows by itself: replies from other servers, edits
                    if (grew != threadSeq) {
                        threadSeq = grew
                        (place as? Place.Thread)?.let { reloadThread(it.focus) }
                    }
                    refreshing = false
                    pulling = false
                }
            }
        }
    }

    private var sharedOnStart: String? = null

    /** A link or words from another app: a post or profile my server finds opens here,
     *  another link goes to the browser, words are searched (the windows' search place). */
    fun openShared(text: String, browser: (String) -> Unit) {
        val words = text.trim().take(500)
        if (words.isBlank()) return
        if (screen != Screen.Main) {
            sharedOnStart = words
            sharedBrowser = browser
            return
        }
        val url = Regex("""https?://\S+""").find(words)?.value?.trimEnd('.', ',', ')', '»', '"')
        if (url == null) {
            openPage("search", words)
            return
        }
        viewModelScope.launch {
            val got = Core.resolve(url)
            when (got.optString("found")) {
                "thread" -> openThread(got.optString("id"))
                "account" -> openProfile(got.optString("id"))
                else -> browser(url)
            }
        }
    }

    private var sharedBrowser: (String) -> Unit = {}

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
        viewModelScope.launch { Core.pause(false); Core.network(onWifi()) }
        watchNetwork()
        watch()
    }

    // phone.stream = "wifi": the live stream only on Wi-Fi — told at every change
    private var networkWatch: ConnectivityManager.NetworkCallback? = null

    private fun connectivity() =
        getApplication<Application>().getSystemService(ConnectivityManager::class.java)

    private fun onWifi(): Boolean {
        val cm = connectivity() ?: return false
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
    }

    private fun watchNetwork() {
        if (networkWatch != null) return
        val cm = connectivity() ?: return
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                val wifi = caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
                    caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
                viewModelScope.launch { Core.network(wifi) }
            }
            override fun onLost(network: Network) {
                viewModelScope.launch { Core.network(onWifi()) }
            }
        }
        try {
            cm.registerDefaultNetworkCallback(cb)
            networkWatch = cb
        } catch (e: RuntimeException) {  // no permission, too many callbacks: as it was
            networkWatch = null
        }
    }

    override fun onCleared() {
        networkWatch?.let { cb -> try { connectivity()?.unregisterNetworkCallback(cb) }
                                 catch (e: RuntimeException) { } }
        networkWatch = null
        super.onCleared()
    }

    fun onBackground() {
        if (screen != Screen.Main) return
        watcher?.cancel()
        viewModelScope.launch { Core.pause(true) }
    }

    // ---- places over the lane ----------------------------------------------------------
    /** Back: the place on top closes; with none, a lane goes back to the overview. */
    // the help's pages gone back from: "forward" brings them again (the windows' →)
    var helpAhead by mutableStateOf(listOf<Place.Page>())

    /** Help: the page gone back from, again. */
    fun helpForward() {
        val next = helpAhead.lastOrNull() ?: return
        helpAhead = helpAhead.dropLast(1)
        places = places + next
        viewModelScope.launch { loadPage(next) }
    }

    fun back(): Boolean {
        if (places.isNotEmpty()) {
            val left = places.last()
            if (left is Place.Page && left.name == "help" && places.dropLast(1).lastOrNull()
                    .let { it is Place.Page && it.name == "help" }) {
                helpAhead = helpAhead + left  // a help page left for the one before it
            }
            if (left is Place.Compose) saveDraft()  // whatever happens next, the text is safe
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

    /** The thread of a post; at: where it stands once loaded — "post", or "first_unread"
     *  (common/links.py THREAD_AT: a card's open_at, a fedtail:threadnew/ link). */
    fun openThread(postId: String, at: String = "post") {
        threadCwOpen = false
        // three columns: the thread pane shows one thread — a new one takes its place
        val keep = if (columns >= 3 && place is Place.Thread) places.dropLast(1) else places
        places = keep + Place.Thread(postId)
        threadPosts = emptyList()
        threadHead = null
        watchThreadProgress(postId)
        viewModelScope.launch {
            val got = Core.thread(postId, at)
            Core.failed(got)?.let { message = it; back(); return@launch }
            threadPosts = parsePosts(got.optJSONArray("posts"))
            threadHead = got.optJSONObject("head")
            // read as it opens, unless by hand — the core's decision (common/lane.py)
            got.optJSONArray("read_on_open")?.let { arr ->
                val now = (0 until arr.length()).map { arr.getString(it) }.toSet()
                markRead(threadPosts.filter { it.id in now || it.sid in now }.map { it.key },
                         inThread = true)
            }
            threadAimAt = got.optString("focus").takeIf { it.isNotBlank() && it != postId }
            threadOpening += 1
        }
    }

    private fun watchThreadProgress(postId: String) {
        progressWatch?.cancel()
        threadProgress = ""
        progressWatch = viewModelScope.launch {
            var rounds = 0
            var saidDone = 0
            while (isActive && rounds++ < 120 && (place as? Place.Thread)?.focus == postId) {
                val got = Core.threadProgress(postId)
                if (Core.failed(got) != null) break
                val stage = got.optString("stage")
                val text = got.optString("text")
                val bar = got.optString("bar")
                threadProgress = if (text.isBlank()) "" else listOf(bar, text)
                    .filter { it.isNotBlank() }.joinToString(" ")
                if (stage == "done" || stage == "failed") { if (++saidDone > 8) break }
                else if (stage.isBlank() && rounds > 5) break  // nothing going on
                delay(1000)
            }
            threadProgress = ""
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
        // the draft kept for it (here, or from another device), or the reply's mentions
        val opened = composeText
        viewModelScope.launch {
            val d = Core.draftStart(replyTo?.sid ?: "")
            if (Core.failed(d) != null || editId != null || quoteId != null) return@launch
            if (place !is Place.Compose || composeText != opened) return@launch // typed meanwhile
            composeText = str(d, "text").ifBlank { composeText }
            if (!d.optBoolean("restored")) return@launch
            str(d, "cw").takeIf { it.isNotBlank() }?.let { composeCw = it; composeCwOn = true }
            str(d, "visibility").takeIf { it.isNotBlank() }?.let { composeVisibility = it }
            if (!d.isNull("language")) composeLang = str(d, "language")
            composeSensitive = d.optBoolean("sensitive")
            d.optJSONObject("poll")?.let { pl ->
                val o = pl.optJSONArray("options") ?: JSONArray()
                pollOptions = (0 until o.length()).map { o.optString(it) }.ifEmpty { listOf("", "") }
                pollExpires = pl.optInt("expires_in", 86400)
                pollMultiple = pl.optBoolean("multiple")
                pollOn = true
            }
            composeHint = str(d, "hint")
        }
        composeVisibility = if (replyTo == null) defaultVisibility else null
        places = places + Place.Compose(replyTo)
    }

    fun send(altOk: Boolean = false, langOk: Boolean = false) {
        val p = place as? Place.Compose ?: return
        if (composeText.isBlank() || sending || uploading > 0) return
        sending = true
        viewModelScope.launch {
            val body = JSONObject().put("text", composeText)
            if (composeCwOn && composeCw.isNotBlank()) body.put("cw", composeCw)
            val edit = editId
            if (edit != null) {
                body.put("edit", edit)
                body.put("media_edit", JSONArray(attachments.filter { it.id.isNotBlank() }.map { a ->
                    JSONObject().put("id", a.id).put("alt", a.alt).also { o ->
                        a.focus?.let { o.put("focus", JSONArray(listOf(it.first, it.second))) } } }))
            } else {
                (p.replyTo?.sid ?: replyToId)?.let { body.put("reply_to", it) }
                composeVisibility?.let { body.put("visibility", it) }
                if (composeLang.isNotBlank()) body.put("lang", composeLang)
                quoteId?.let { body.put("quote", it) }
                val media = attachments.filter { it.token.isNotBlank() }
                if (media.isNotEmpty()) {
                    body.put("media", JSONArray(media.map { a ->
                        JSONObject().put("token", a.token).put("alt", a.alt).also { o ->
                            a.focus?.let { o.put("focus", JSONArray(listOf(it.first, it.second))) }
                            if (a.cover.isNotBlank()) o.put("cover", a.cover)
                        } }))
                    if (composeSensitive) body.put("sensitive", true)
                } else if (pollOn) {
                    val opts = pollOptions.map { it.trim() }.filter { it.isNotBlank() }
                    if (opts.size >= 2) body.put("poll", JSONObject().put("options", JSONArray(opts))
                        .put("expires_in", pollExpires).put("multiple", pollMultiple))
                }
                if (altOk) body.put("alt_ok", true)
                if (langOk) body.put("lang_ok", true)
                composeFrom?.let { body.put("account", it) }
                if (composeWhen.isNotBlank()) body.put("scheduled_at", composeWhen.replace("T", " "))
            }
            val got = Core.post(body)
            sending = false
            Core.failed(got)?.let { message = it; return@launch }
            got.optJSONObject("ask_alt")?.let { a ->
                asking = Asking.Confirm(str(a, "text"), { send(altOk = true) }, str(a, "title"),
                    str(a, "send"), str(a, "describe"))
                return@launch
            }
            got.optJSONObject("ask_lang")?.let { a ->  // post.lang_check: another language?
                asking = Asking.Choose(str(a, "title"), str(a, "text"),
                    listOf("switch" to str(a, "switch"), "send" to str(a, "send")), "") { key, _ ->
                    if (key == "switch") composeLang = str(a, "lang")
                    send(altOk = true, langOk = true)
                }
                return@launch
            }
            str(got, "message").takeIf { it.isNotBlank() }?.let { message = it }
            val sentKey = draftKey()
            launch { Core.draftDrop(sentKey) }  // sent: its draft goes, here and elsewhere
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
        if (Core.failed(got) == null) {
            threadPosts = parsePosts(got.optJSONArray("posts"))
            threadHead = got.optJSONObject("head")
            // read as it opens, unless by hand — the core's decision (common/lane.py)
            got.optJSONArray("read_on_open")?.let { arr ->
                val now = (0 until arr.length()).map { arr.getString(it) }.toSet()
                markRead(threadPosts.filter { it.id in now || it.sid in now }.map { it.key },
                         inThread = true)
            }
        }
    }

    /** The head's "Follow": the thread followed, or left; the head says so at once. */
    fun toggleThreadSub() {
        val head = threadHead ?: return
        val focus = (place as? Place.Thread)?.focus ?: return
        viewModelScope.launch {
            val got = Core.threadAct(if (head.optBoolean("subscribed")) "unsub" else "sub",
                head.optString("sid"))
            message = Core.failed(got) ?: got.optString("message").ifBlank { null }
            reloadThread(focus)
        }
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

    /** A link tapped in a post: a post my server knows opens as a thread, a person as
     *  their profile; else the browser. */
    fun openLink(url: String, openBrowser: (String) -> Unit) {
        // the program's own links (common/links.py): a thread, a person
        if (url.startsWith("fedtail:")) {
            val parts = url.removePrefix("fedtail:").split("/", limit = 2)
            val arg = parts.getOrNull(1).orEmpty()
            when (parts[0]) {
                "thread", "post" -> if (arg.isNotBlank()) openThread(arg)
                "threadnew" -> if (arg.isNotBlank()) openThread(arg, "first_unread")
                "account", "profile" -> if (arg.isNotBlank()) openProfile(arg)
                // the rest the windows' way (common/links.py): a #tag's place, a fediverse
                // address resolved here, a post's edits, its time…
                else -> runLink(url)
            }
            return
        }
        // a #tag (its server's /tags/name): the tag's place here, as the windows open it
        Regex("""^https?://[^/]+/tags/([^/?#]+)/?$""").find(url)?.let { m ->
            openPage("tag", java.net.URLDecoder.decode(m.groupValues[1], "UTF-8"))
            return
        }
        viewModelScope.launch {
            val got = Core.resolve(url)
            val id = got.optString("id")
            when {
                got.optString("found") == "thread" && id.isNotBlank() -> openThread(id)
                got.optString("found") == "account" && id.isNotBlank() -> openProfile(id)
                else -> openBrowser(url)
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
                o.optString("thread").takeIf { it.isNotBlank() }
                    ?.let { openThread(it, o.optString("at").ifBlank { "post" }) }
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
        // the place every interface draws (common/syncplace.py): where, the login, the key
        // — taken from another device, or out of the journal with its password
        openPage("sync")
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

    /** A lane's rule in the lane editor; a lane that isn't a rule of its own (a list's, a
     *  tag group's: "list:…", "tags:…") — the editor's list of every lane. */
    fun editLane(name: String) {
        if (':' in name) openPage("lanes") else openPage("lane", name)
    }

    /** A place: pushed over what is open (a tab or the next rows of the same place: in its stead). */
    fun openPage(name: String, arg: String = "", tab: String = "", cursor: String = "") {
        val top = place
        if (top is Place.Page && top.name == name && top.arg == arg && cursor.isNotBlank()) {
            moreRows(top, tab, cursor)
            return
        }
        val p = Place.Page(name, arg, tab)
        if (name == "help") helpAhead = emptyList()  // a new way through the help
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
            // the cards on screen: "read up to here" is counted by the core, by time
            val shown = (if (place is Place.Thread) threadPosts else posts).map { it.id }
            val got = Core.link(url, confirmed, chosen, shown)
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
        got.optJSONArray("read")?.let { arr -> paintRead((0 until arr.length()).map { arr.getString(it) }) }
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
            str(o, "thread").isNotBlank() ->
                openThread(str(o, "thread"), str(o, "at").ifBlank { "post" })
            str(o, "account").isNotBlank() -> openProfile(str(o, "account"))
            str(o, "page") == "settings" ->  // its own screen, not the place's form
                openSettings(str(o, "arg").ifBlank { str(o, "tab") })
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
    /** Marked read by the core ("read up to here"): the cards say so, nothing sent again. */
    private fun paintRead(ids: List<String>) {
        val done = ids.toSet()
        val seen = { p: PostItem -> if (p.id in done || p.sid in done) p.copy(unread = false) else p }
        posts = posts.map(seen)
        threadPosts = threadPosts.map(seen)
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

    /** Where the formatting buttons stand: "left", "right", "top", "bottom" ("" — none). */
    fun formatPlace(): String = editorFacts?.optString("format_place") ?: ""

    /** The editor's formatting buttons (post.format_bar): (name, face, tooltip); none — []. */
    fun formatBar(): List<Triple<String, String, String>> {
        val arr = editorFacts?.optJSONArray("format_bar") ?: return emptyList()
        return (0 until arr.length()).map {
            val o = arr.getJSONObject(it)
            Triple(o.optString("name"), o.optString("face"), o.optString("tip"))
        }
    }
    var composeFrom by mutableStateOf<String?>(null) // all accounts in one: whose post
    var composeWhen by mutableStateOf("")       // "2026-10-26T09:30": send then (local time)
    var composeHint by mutableStateOf("")       // "draft restored", "draft saved"
    var previewing by mutableStateOf<JSONObject?>(null)
    private var discarded = false

    /** The draft's name, as the core's (common/compose.draft_key). */
    fun draftKey(): String {
        val p = place as? Place.Compose
        return when {
            editId != null -> "edit:$editId"
            quoteId != null -> "quote:$quoteId"
            p?.replyTo != null -> "reply:${p.replyTo.sid}"
            replyToId != null -> "reply:$replyToId"
            else -> "new"
        }
    }

    private fun snapshot() = JSONObject().put("text", composeText)
        .put("cw", if (composeCwOn) composeCw else "")
        .put("visibility", composeVisibility ?: defaultVisibility)
        .put("language", composeLang.ifBlank { JSONObject.NULL })
        .put("sensitive", composeSensitive)
        .put("poll", if (pollOn) JSONObject().put("options", JSONArray(pollOptions))
            .put("expires_in", pollExpires).put("multiple", pollMultiple) else JSONObject.NULL)

    /** Kept as it is now (post.drafts_autosave), or gone when emptied. */
    fun saveDraft() {
        if (place !is Place.Compose || discarded) return
        val key = draftKey()
        val snap = snapshot()
        viewModelScope.launch {
            val got = Core.draftSave(key, snap)
            if (Core.failed(got) == null) composeHint = str(got, "hint")
        }
    }

    /** "Discard": the text and its draft gone, after the question. */
    fun discard(sure: Boolean = false) {
        if (!sure) {
            val app = getApplication<Application>()
            asking = Asking.Confirm(app.getString(R.string.discard_q), { discard(true) },
                app.getString(R.string.discard))
            return
        }
        val key = draftKey()
        discarded = true
        viewModelScope.launch { Core.draftDrop(key) }
        places = places.dropLast(1)
        clearEditor()
    }

    /** The post as it will read: the core's preview (Qt's), to send from there. */
    fun preview() {
        viewModelScope.launch {
            val body = JSONObject().put("text", composeText)
                .put("cw", if (composeCwOn) composeCw else "")
                .put("media", attachments.size)
            val got = Core.preview(body)
            Core.failed(got)?.let { message = it; return@launch }
            previewing = got
        }
    }

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
        composeWhen = ""
        composeHint = ""
        previewing = null
        discarded = false
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

    // what the editor says under the text as it is typed: a chain's parts, the #CamelCase
    // hint for screen readers (web compose_check, the windows' counter)
    var composeHints by mutableStateOf("")
    var composeNewcomers by mutableStateOf("") // "⚠ @eve wasn't in this private talk"
    var composeCounted by mutableStateOf<Triple<String, String, Int>?>(null) // (text, cw, n)

    suspend fun checkCompose() {
        val body = JSONObject().put("text", composeText)
            .put("cw", if (composeCwOn) composeCw else "")
        // a reply in a private talk: someone typed in who wasn't in it (feeds.md §11, 5)
        val answered = (places.lastOrNull { it is Place.Compose } as? Place.Compose)?.replyTo
        (answered?.sid ?: replyToId)?.let { body.put("reply_to", it) }
        // a reply's own visibility is the core's call at sending: a private one stays so
        (composeVisibility ?: answered?.visibility?.takeIf { it.isNotBlank() })
            ?.let { body.put("visibility", it) }
        val got = Core.composeCheck(body)
        if (Core.failed(got) != null) return
        composeNewcomers = got.optString("newcomers")
        // the windows' count (a chain: its longest part, each counted on its own)
        composeCounted = if (got.has("n")) Triple(composeText, composeCw, got.optInt("n")) else null
        composeHints = listOf(got.optString("chain"), got.optString("camel"))
            .filter { it.isNotBlank() }.joinToString("\n")
    }

    /** "Another language…": a code the editor lists from then on; picked at once. */
    fun addLanguage(code: String) {
        viewModelScope.launch {
            val got = Core.addLanguage(code.trim())
            Core.failed(got)?.let { message = it; return@launch }
            composeLang = got.optString("code")
            loadEditorFacts()
        }
    }

    /** The words of "Another language…" (its row in the list, "\u0000other"). */
    fun otherLanguageWords(): String? {
        val arr = editorFacts?.optJSONArray("languages") ?: return null
        return (0 until arr.length()).map { arr.getJSONArray(it) }
            .firstOrNull { it.optString(0).startsWith("\u0000") }?.optString(1)
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
                Attachment("", "", str(it, "kind"), str(it, "alt"), str(it, "id"), str(it, "url"),
                    focus = it.optJSONArray("focus")?.let { f ->
                        f.optDouble(0).toFloat() to f.optDouble(1).toFloat() })
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
        // post.quote_prefix, the leading @mentions left out — the windows' quote
        viewModelScope.launch {
            val got = Core.quoteLines(p.text.trim())
            val quoted = if (Core.failed(got) == null) got.optString("text")
                         else p.text.trim().lines().joinToString("\n") { "> $it" } + "\n\n"
            composeText = composeText.trimEnd() + "\n" + quoted
        }
    }

    fun detach(a: Attachment) {
        attachments = attachments - a
    }

    /** Where a picture's previews centre on (tapped on it): -1…1, y up. */
    fun setFocus(a: Attachment, x: Float, y: Float) {
        attachments = attachments.map {
            if (it.token == a.token && it.id == a.id) it.copy(focus = x to y) else it
        }
    }

    /** A video's or sound's cover: a picture uploaded the same way, shown until it plays. */
    fun setCover(a: Attachment, uri: Uri) {
        uploadFor(uri) { token ->
            attachments = attachments.map {
                if (it.token == a.token && it.id == a.id) it.copy(cover = token,
                    coverPreview = uri.toString()) else it
            }
        }
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

    private fun parseButton(o: JSONObject?): PlaceButton? = o?.let { b ->
        val act = b.optJSONArray("act") ?: JSONArray()
        PlaceButton(b.optString("label"), List(act.length()) { act.optString(it) },
            b.optBoolean("primary"), b.optString("tip"))
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
                    r.optJSONObject("account")?.let { parseAccount(it) }, str(r, "html"),
                    r.optJSONArray("qr")?.let { q -> (0 until q.length()).map { q.optString(it) } }
                        ?: emptyList())
            },
            form = (0 until form.length()).map { form.getJSONObject(it) }.map { f ->
                val ch = f.optJSONArray("choices") ?: JSONArray()
                PageField(str(f, "name"), str(f, "label"), f.optString("kind", "line"),
                    if (f.isNull("value")) null else f.opt("value"),
                    (0 until ch.length()).map { ch.getJSONArray(it) }
                        .map { it.optString(0) to it.optString(1) }, str(f, "tip"),
                    f.optBoolean("scan", false))
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
            // from their own server: how many came ("12 posts from host · old posts…")
            str(got, "said").takeIf { it.isNotBlank() }?.let { message = it }
        }
    }

    private fun parsePosts(arr: JSONArray?): List<PostItem> =
        if (arr == null) emptyList() else (0 until arr.length()).map { parsePost(arr.getJSONObject(it)) }

    private fun str(o: JSONObject?, key: String): String =
        if (o == null || o.isNull(key)) "" else o.optString(key)

    /** The lane's rows in the server's order (oldest first): its posts and, among them, the
     *  events it takes (web lane "events": {key, event, before}) — each before the post it
     *  came before, the rest after the last; a lane of events only has nothing else. */
    private fun withEvents(list: List<PostItem>, events: JSONArray?): List<PostItem> {
        if (events == null || events.length() == 0) return list
        val before = HashMap<String, MutableList<PostItem>>()
        val after = mutableListOf<PostItem>()
        for (i in 0 until events.length()) {
            val e = events.optJSONObject(i) ?: continue
            val row = parseEvent(e) ?: continue
            val at = str(e, "before")
            if (at.isBlank()) after += row else before.getOrPut(at) { mutableListOf() } += row
        }
        return list.flatMap { p -> (before[p.id] ?: emptyList()) + p } + after
    }

    private fun pairs(arr: JSONArray?): List<Pair<String, String>> =
        if (arr == null) emptyList() else (0 until arr.length()).mapNotNull { arr.optJSONArray(it) }
            .map { it.optString(0) to it.optString(1) }

    /** An event's row ({key, event: EventParts}) as a row of the lane: a PostItem whose
     *  `event` is set, its key "event:<id>" (what Core.read marks seen). */
    private fun parseEvent(e: JSONObject): PostItem? {
        val key = str(e, "key").takeIf { it.isNotBlank() } ?: return null
        val x = e.optJSONObject("event") ?: return null
        val ev = EventItem(kind = str(x, "kind"), people = pairs(x.optJSONArray("people")),
            more = str(x, "more"), what = str(x, "what"), whenText = str(x, "when"),
            notice = str(x, "notice"), post = str(x, "post"), postLink = str(x, "post_link"),
            hide = str(x, "hide"), hideTip = str(x, "hide_tip"),
            answers = pairs(x.optJSONArray("answers")),
            answerWords = pairs(x.optJSONArray("answer_words")), tip = str(x, "tip"))
        return PostItem(key = key, id = key, sid = key, alias = "", name = "", handle = "",
            avatar = "", created = "", text = "", warning = "", sensitive = false,
            media = emptyList(), card = null, poll = "", html = "", url = "", shared = false,
            bookmarked = false, unread = x.optBoolean("unread"), sharedBy = "",
            contextHandle = "", contextText = "", replies = 0, shares = 0, likes = 0,
            liked = false, number = null, depth = 0, event = ev)
    }

    /** A line around a card ({text, link}) as (words, link); null — none. */
    private fun bit(o: JSONObject?): Pair<String, String>? =
        str(o, "text").takeIf { it.isNotBlank() }?.let { it to str(o, "link") }

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
            openAt = o.optString("open_at").ifBlank { "post" },
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
                str(it, "image"), str(it, "description")) },
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
            pollShares = poll?.optJSONArray("options")?.let { a ->
                (0 until a.length()).map { a.getJSONObject(it).optInt("share") } } ?: emptyList(),
            pollMine = poll?.optJSONArray("mine")?.let { a ->
                (0 until a.length()).map { a.optInt(it) }.toSet() } ?: emptySet(),
            pollSummary = poll?.let { str(it, "summary") } ?: "",
            pollOpen = poll != null && !poll.optBoolean("voted") && !poll.optBoolean("expired") &&
                !o.optBoolean("own"),
            own = o.optBoolean("own"),
            edited = o.optBoolean("edited"),
            visibility = str(o, "visibility"),
            nameHtml = str(acc, "name_html"),
            nameColor = str(acc, "color"),
            labels = o.optJSONObject("words")?.optJSONArray("meta")?.let { m ->
                (0 until m.length()).mapNotNull { m.optJSONObject(it)?.optString("text") }
                    .filter { it.isNotBlank() }.joinToString(" · ") } ?: "",
            reactions = o.optJSONObject("words")?.optString("reactions") ?: "",
            meta = o.optJSONObject("words")?.optJSONArray("meta")?.let { a ->
                // the time stands in the head already
                (0 until a.length()).mapNotNull { a.optJSONObject(it) }
                    .filter { str(it, "kind") != "time" }.mapNotNull { bit(it) } } ?: emptyList(),
            foldedBy = o.optJSONObject("words")?.takeIf { it.optBoolean("folded") }?.let { w ->
                str(w, "warning").split(" · ").firstOrNull().orEmpty() } ?: "",
            quoteLine = bit(o.optJSONObject("words")?.optJSONObject("quote")),
            quoteOff = o.optJSONObject("words")?.let { it.isNull("quote") } ?: false,
            conversation = bit(o.optJSONObject("words")?.optJSONObject("conversation")),
            boosted = bit(o.optJSONObject("words")?.optJSONObject("boosted")),
            contextLine = bit(o.optJSONObject("words")?.optJSONObject("context")),
            newcomer = bit(o.optJSONObject("words")?.optJSONObject("newcomer")),
            threadNews = bit(o.optJSONObject("words")?.optJSONObject("thread_news")),
            myReplies = o.optJSONObject("words")?.optJSONArray("my_replies")?.let { a ->
                (0 until a.length()).mapNotNull { bit(a.optJSONObject(it)) } } ?: emptyList(),
            via = o.optJSONObject("via")?.optString("text") ?: "",
            viaColor = o.optJSONObject("via")?.optString("color") ?: "",
            quoteId = str(o.optJSONObject("quote"), "id"),
            quoteWho = o.optJSONObject("quote")?.optJSONObject("account")?.let { a ->
                str(a, "name").ifBlank { str(a, "handle") } } ?: "",
            quoteText = o.optJSONObject("quote")?.let { q ->
                str(q, "text").ifBlank { str(q, "note") } } ?: "",
        )
    }
}
