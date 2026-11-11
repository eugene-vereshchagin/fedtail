package online.dmesg.fedtail

import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.RadioButton
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.IconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.fromHtml
import androidx.compose.foundation.text.appendInlineContent
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.em
import coil.compose.AsyncImage
import coil.request.ImageRequest
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.abs
import androidx.compose.foundation.combinedClickable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.launch
import kotlinx.coroutines.coroutineScope
import androidx.compose.foundation.interaction.DragInteraction

/** A long press on a card (its words too, but a tag): its menu, the sheet of ⋯ — set by
 *  the card around them. */
val LocalCardHold = androidx.compose.runtime.compositionLocalOf<(() -> Unit)?> { null }

/** What a card can ask for; the lane and the thread give the same (AppModel.cardActions). */
class CardActions(
    val open: (PostItem) -> Unit, val reply: (PostItem) -> Unit, val like: (PostItem) -> Unit,
    val media: (List<MediaItem>, Int) -> Unit,
    val link: (String) -> Unit,     // a link in a post: a thread here if my server knows it
    val alias: (String) -> Unit,
    val share: (PostItem) -> Unit, val bookmark: (PostItem) -> Unit,
    val info: suspend (PostItem) -> JSONObject,      // the ⋯ menu: followed? its address
    val thread: (PostItem, String) -> Unit,          // sub / unsub the thread
    val browser: (String) -> Unit,
    val expandCw: Boolean = false,                   // ui.expand_cw or ui.arts_mode: CWs open
    val profile: (String) -> Unit = {},              // an account's id: its profile
    val menu: (suspend (PostItem) -> JSONObject)? = null, // the windows' ⋯ (common/actions)
    val runLink: (String) -> Unit = {},              // a fedtail: link of that menu
    // a long press on a #tag (a tap too, reading.tag_click = "menu" — click true): the
    // windows' menu of it — [(words, fedtail: link)]
    val tagMenu: suspend (String, Boolean) -> List<Pair<String, String>> = { _, _ -> emptyList() },
    // a long press on a picture: its own menu, the windows' right click on it
    // (common/actions.media_items: save, open, copy, the image searches) — [{kind, label, url, text}]
    val mediaMenu: (suspend (PostItem, Int) -> JSONArray)? = null,
    val page: (String, String) -> Unit = { _, _ -> }, // a place of that menu (lists, translate…)
    val quoteReply: (PostItem) -> Unit = {},
    val vote: (PostItem, List<Int>) -> Unit = { _, _ -> },
    val actAs: (PostItem, String, String) -> Unit = { _, _, _ -> }, // post, account, fav|boost|reply
    val pollRefresh: (PostItem) -> Unit = {},
    val bookmarkButton: Boolean = false,             // ui.bookmark_button: a bookmark beside ↩ ♻ ♡
    val aliasTaps: Boolean = false,                  // ui.command_line: #alias into the line
    val holdSelects: Boolean = true,                 // phone.hold_text: a long press selects words
    // a private message among posts (the core's: ui.direct_highlight, the theme's
    // shape.direct): "frame", "fill", "badge" or "none"; its colour (null: violet)
    val directMark: String = "none",
    val directColor: Color? = null,
    val onDirect: Color? = null,
)

fun AppModel.cardActions(openBrowser: (String) -> Unit, cwOpen: Boolean = false) = CardActions(
    open = { openThread(it.sid, it.openAt) }, reply = { compose(it) }, like = { act(it, "like") },
    media = { list, i -> openMedia(list, i) }, link = { openLink(it, openBrowser) },
    alias = { putAlias(it) }, share = { act(it, "share") }, bookmark = { act(it, "bookmark") },
    info = { menuOf(it) }, thread = { p, what -> threadAct(p, what) }, browser = openBrowser,
    expandCw = expandCw || cwOpen, profile = { openProfile(it) }, menu = { postMenu(it) },
    runLink = { runLink(it) }, page = { name, arg -> openPage(name, arg) },
    tagMenu = { url, click ->
        val arr = Core.tagMenu(url, click).optJSONArray("items") ?: org.json.JSONArray()
        (0 until arr.length()).map { arr.getJSONObject(it).let { o -> o.optString("label") to o.optString("url") } }
    },
    mediaMenu = { p, i -> Core.mediaMenu(p.sid, i).optJSONArray("items") ?: JSONArray() },
    quoteReply = { quoteReply(it) }, vote = { p, choices -> vote(p, choices) },
    actAs = { p, tag, action -> actAs(p, tag, action) }, pollRefresh = { pollRefresh(it) },
    bookmarkButton = bookmarkButton, aliasTaps = commandLine, holdSelects = holdSelects,
    directMark = directMark, directColor = hexColor(themeColors["direct"]),
    onDirect = hexColor(themeColors["on-direct"]))

// a server's emoji as the core writes it (web/server.py with_emojis): its picture's address
private val EMOJI = Regex("""<img\b[^>]*\bclass="emoji"[^>]*\bsrc="([^"]*)"[^>]*>""")
private const val EMOJI_MARK = '\uE000'
private const val INLINE_TAG = "androidx.compose.foundation.text.inlineContent"

/** HTML with each emoji picture as one mark (its address kept, in order). */
fun emojiMarks(html: String): Pair<String, List<String>> {
    val urls = mutableListOf<String>()
    val text = EMOJI.replace(html) { m ->
        urls += m.groupValues[1].replace("&amp;", "&")
        EMOJI_MARK.toString()
    }
    return text to urls
}

/** The text up to end, each mark a picture in its place (one character each: every
 *  style and link keeps its offsets). */
fun AnnotatedString.Builder.appendWithEmoji(text: String, urls: List<String>) {
    var k = 0
    for (ch in text) {
        if (ch == EMOJI_MARK && k < urls.size) appendInlineContent("emoji:" + urls[k++], "\uFFFD")
        else append(ch)
    }
}

/** The pictures of the emoji in a text, for Text's inlineContent: a line's height each. */
fun emojiContent(words: AnnotatedString): Map<String, androidx.compose.foundation.text.InlineTextContent> =
    words.getStringAnnotations(INLINE_TAG, 0, words.length).map { it.item }
        .filter { it.startsWith("emoji:") }.distinct().associateWith { id ->
            androidx.compose.foundation.text.InlineTextContent(
                androidx.compose.ui.text.Placeholder(1.25.em, 1.25.em,
                    androidx.compose.ui.text.PlaceholderVerticalAlign.TextCenter)) {
                AsyncImage(model = id.removePrefix("emoji:"), contentDescription = null,
                    modifier = Modifier.fillMaxSize())
            }
        }

/** A name that may hold :emoji: (the core's name_html), as text with their pictures. */
fun nameText(name: String, html: String): AnnotatedString {
    if (html.isBlank()) return AnnotatedString(name)
    return try {
        val (marked, urls) = emojiMarks(html)
        val a = AnnotatedString.fromHtml(marked)
        buildAnnotatedString { appendWithEmoji(a.text.trim(), urls) }
    } catch (e: Exception) {
        AnnotatedString(name)
    }
}

/** A post's HTML as text, its links coloured and marked "URL", the server's emoji as
 *  their pictures. Plain marks, not Compose's own link handling: that takes every tap
 *  on the text, and a tap beside a link must open the thread (PostWords decides). */
fun postText(html: String, plain: String, linkColor: Color): AnnotatedString {
    if (html.isBlank()) return AnnotatedString(plain)
    return try {
        val (marked, urls) = emojiMarks(html)
        val a = AnnotatedString.fromHtml(marked)
        var end = a.length
        while (end > 0 && a[end - 1].isWhitespace()) end--
        buildAnnotatedString {
            appendWithEmoji(a.text.substring(0, end), urls)
            a.spanStyles.forEach { r ->
                if (r.start < end) addStyle(r.item, r.start, minOf(r.end, end))
            }
            a.getLinkAnnotations(0, end).forEach { r ->
                val url = (r.item as? LinkAnnotation.Url)?.url ?: return@forEach
                val stop = minOf(r.end, end)
                addStyle(SpanStyle(color = linkColor), r.start, stop)
                addStringAnnotation("URL", url, r.start, stop)
            }
        }
    } catch (e: Exception) {
        AnnotatedString(plain)
    }
}

/** A post's words: a tap on a link follows it, a tap anywhere else is the card's own; a
 *  long press on a #tag — the windows' right-click menu of it (common/links.tag_menu: as
 *  its author writes it, everywhere, muted; the phone had none, 02.11). Elsewhere a long
 *  press selects the words (phone.hold_text = "select": the post's menu took it, and
 *  nothing in a post could be copied, 10.11), or opens the post's menu ("menu"). */
@Composable
private fun PostWords(words: AnnotatedString, onLink: (String) -> Unit,
                      runLink: (String) -> Unit, tagMenu: suspend (String, Boolean) -> List<Pair<String, String>>,
                      selects: Boolean, onTap: () -> Unit) {
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    val link by rememberUpdatedState(onLink)
    val tap by rememberUpdatedState(onTap)
    var menu by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
    val scope = rememberCoroutineScope()
    val scale = LocalPostScale.current  // [font] post_scale: a theme's posts larger
    val emoji = remember(words) { emojiContent(words) }
    val hold by rememberUpdatedState(LocalCardHold.current)
    fun urlAt(pos: androidx.compose.ui.geometry.Offset): String? {
        val at = layout?.getOffsetForPosition(pos) ?: return null
        return words.getStringAnnotations("URL", at, at).firstOrNull()?.item
    }
    val text = @Composable {
        Text(words, fontSize = 15.sp * scale, lineHeight = 21.sp * scale, onTextLayout = { layout = it },
            inlineContent = emoji,
            modifier = Modifier.pointerInput(words, selects) {
                detectTapGestures(
                    // selecting: no long press of ours but a tag's, the selection takes it
                    onLongPress = { pos ->
                        val url = urlAt(pos)
                        if (url != null && url.startsWith("fedtail:tag/")) {
                            scope.launch { menu = tagMenu(url, false) }
                        } else if (!selects) hold?.invoke()
                    },
                    onTap = { pos ->
                        val url = urlAt(pos)
                        when {
                            url == null -> tap()
                            // reading.tag_click = "menu": a tap gives the tag's menu (the
                            // core says whether; no items — the tag opens as before)
                            url.startsWith("fedtail:tag/") -> scope.launch {
                                val got = tagMenu(url, true)
                                if (got.isNotEmpty()) menu = got else link(url)
                            }
                            else -> link(url)
                        }
                    })
            })
    }
    Box {
        if (selects) SelectionContainer { text() } else text()
        DropdownMenu(expanded = menu.isNotEmpty(), onDismissRequest = { menu = emptyList() }) {
            menu.forEach { (said, url) ->
                DropdownMenuItem(text = { Text(said) }, onClick = { menu = emptyList(); runLink(url) })
            }
        }
    }
}

/** Read marks when scrolling stops (read.mark_read): what the core's rule says is read —
 *  the windows' own (common/lane.seen): whole on screen, or a card taller than the
 *  screen whose end came into view, or anything on screen at the list's end, or a card
 *  glimpsed and then scrolled past. The phone counted only cards whole on screen, and a
 *  tall one never was (31.10). And, as the windows' and the web page's: a card the
 *  screen went over whole while the finger scrolled it — a quick run through pictures
 *  never stopped on them and left them unread (10.11). Not a jump ("to the new"). */
@Composable
fun MarkWhileScrolling(state: LazyListState, on: Boolean, dwellMs: Long,
                       mark: (List<String>) -> Unit) {
    val glimpsed = remember(state) { mutableSetOf<String>() }
    val where = remember(state) { HashMap<String, Int>() }  // a card's index, last seen
    val swept = remember(state) { mutableSetOf<String>() }  // whole on screen, scrolling
    val byHand = remember(state) { booleanArrayOf(false) }  // this scroll is the finger's
    LaunchedEffect(state, on) {
        if (!on) return@LaunchedEffect
        launch {
            state.interactionSource.interactions.collect {
                if (it is DragInteraction.Start) byHand[0] = true
            }
        }
        // every frame of a scroll by hand (the fling after it too): who is whole on screen
        snapshotFlow { state.layoutInfo }.collect { info ->
            if (!state.isScrollInProgress || !byHand[0]) return@collect
            val vtop = info.viewportStartOffset
            val vbot = info.viewportEndOffset
            info.visibleItemsInfo.forEach {
                val key = it.key as? String ?: return@forEach
                val end = it.offset + it.size
                val whole = it.offset >= vtop - 2 && end <= vbot + 2
                val tallDone = it.size > vbot - vtop && end in (vtop + 1)..(vbot + 2)
                if (whole || tallDone) swept += key
            }
        }
    }
    LaunchedEffect(state, on, dwellMs) {
        if (!on) return@LaunchedEffect
        snapshotFlow { state.isScrollInProgress to state.layoutInfo.visibleItemsInfo.size }
            .collect { (scrolling, _) ->
                if (scrolling) return@collect
                byHand[0] = false
                delay(dwellMs)  // read.dwell_ms, as the windows'
                val info = state.layoutInfo
                val vtop = info.viewportStartOffset
                val cards = JSONArray()
                val shown = HashSet<String>()
                // seen whole on the way: said to the core as whole on screen
                val went = swept.toList()
                swept.clear()
                went.forEach { cards.put(JSONObject().put("key", it).put("top", vtop)
                    .put("bottom", vtop + 1)) }
                info.visibleItemsInfo.forEach {
                    val key = it.key as? String ?: return@forEach
                    shown += key
                    where[key] = it.index
                    if (key in went) return@forEach
                    cards.put(JSONObject().put("key", key).put("top", it.offset)
                        .put("bottom", it.offset + it.size))
                }
                // glimpsed before and now above the screen: scrolled past, read
                val first = info.visibleItemsInfo.firstOrNull()?.index ?: 0
                glimpsed.filter { it !in shown && (where[it] ?: Int.MAX_VALUE) < first }
                    .forEach { cards.put(JSONObject().put("key", it).put("top", vtop - 2)
                        .put("bottom", vtop - 1)) }
                val got = Core.seen(cards, vtop, info.viewportEndOffset,
                    !state.canScrollForward, glimpsed)
                if (Core.failed(got) != null) return@collect
                val read = got.optJSONArray("read") ?: JSONArray()
                val part = got.optJSONArray("glimpsed") ?: JSONArray()
                val readKeys = (0 until read.length()).map { read.getString(it) }
                glimpsed.removeAll(readKeys.toSet())
                (0 until part.length()).forEach { glimpsed += part.getString(it) }
                if (readKeys.isNotEmpty()) mark(readKeys)
            }
    }
}

/** The card on top of the screen once the scroll stands: where the lane opens next time
 *  (LaneModel.stood — the desktop's windows, the terminal and the web page say it too). */
@Composable
fun StoodWhileScrolling(state: LazyListState, shown: (List<String>) -> Unit = {},
                        stood: (String, Boolean) -> Unit) {
    LaunchedEffect(state) {
        snapshotFlow { state.isScrollInProgress to state.firstVisibleItemIndex }
            .collect { (scrolling, _) ->
                if (scrolling) return@collect
                delay(350)
                val info = state.layoutInfo
                shown(info.visibleItemsInfo.mapNotNull { it.key as? String })
                // the last card seen whole — what was read last (LaneModel.stood); one
                // taller than the screen, none whole: the one on top
                val cards = info.visibleItemsInfo.filter {
                    it.offset + it.size > info.viewportStartOffset && it.key is String }
                (cards.lastOrNull { it.offset >= info.viewportStartOffset &&
                    it.offset + it.size <= info.viewportEndOffset } ?: cards.firstOrNull())
                    ?.let { stood(it.key as String, !state.canScrollForward) }
            }
    }
}

/** A lane opened anew stands where the core says reading starts (byCore, start: the card's
 *  key, none — the newest end: feed.start_at and "new below", as on the desktop); "to new"
 *  goes to the first unread. Never jumps after. */
suspend fun aim(state: LazyListState, posts: List<PostItem>, newestFirst: Boolean, before: Int = 0,
                divider: String? = null, byCore: Boolean = false, start: String? = null,
                bottom: Boolean = false): Int {
    if (posts.isEmpty()) return -1
    val firstUnread = posts.indexOfFirst { it.unread }
    // the core says the post's id; a card's key may be its own ("conv:…"): either
    val chosen = if (byCore) posts.indexOfFirst { it.key == start || it.id == start }
        else firstUnread
    val at = when {
        chosen >= 0 -> chosen
        newestFirst -> 0
        else -> posts.size - 1
    }
    // before: items the list holds ahead of the posts ("earlier" at the top); "new below"
    // is an item too: one more ahead of every post from it on — and it is shown itself
    val line = divider?.let { d -> posts.indexOfFirst { it.key == d } } ?: -1
    val index = before + at + if (line in 0..at) (if (line == at) 0 else 1) else 0
    state.scrollToItem(index)
    // bottom: the card read last stands at the screen's bottom, as it was read
    if (bottom && chosen >= 0) {
        val info = state.layoutInfo
        info.visibleItemsInfo.firstOrNull { it.index == index }?.let { card ->
            val room = info.viewportEndOffset - info.viewportStartOffset - card.size - 8
            if (room > 0) state.scrollBy(-room.toFloat())
        }
    }
    return if (chosen >= 0) index else -1
}

/** The card a lane opened on (index) held where it stands — its top on top, or its bottom
 *  at the screen's bottom — while the pictures around it come in: the first card on
 *  screen growing pushed it down, and the lane showed older posts, read ones (the web page
 *  did that, 29.10). Till the reader drags the list, or HOLD_MS. */
suspend fun holdPlace(state: LazyListState, index: Int, bottom: Boolean) {
    if (index < 0) return
    var moved = false
    coroutineScope {
        val watch = launch {
            state.interactionSource.interactions.collect { if (it is DragInteraction.Start) moved = true }
        }
        withTimeoutOrNull(HOLD_MS) {
            snapshotFlow {
                val info = state.layoutInfo
                info.visibleItemsInfo.firstOrNull { it.index == index }?.let {
                    Triple(it.offset, it.size, info.viewportEndOffset)
                }
            }.takeWhile { !moved }.collect { pos ->  // a drag by the reader: let go
                if (pos == null) { state.scrollToItem(index); return@collect }
                val (offset, size, end) = pos
                val want = if (bottom) end - 8 - size else 0
                if (abs(offset - want) > 2) state.scrollBy((offset - want).toFloat())
            }
        }
        watch.cancel()
    }
}

const val HOLD_MS = 10_000L

@Composable
fun PostList(
    posts: List<PostItem>, state: LazyListState, divider: Pair<String, String>?,
    act: CardActions, hideSensitive: Boolean, thread: Boolean = false, focus: String? = null,
    footer: (@Composable () -> Unit)? = null,
    header: (@Composable () -> Unit)? = null,
    emptyText: String? = null, // why it is empty, as the windows say it (a filter on…)
    prefetch: String = "off",  // feed.prefetch: "previews" | "all" — pictures ahead of reading
    busy: Boolean = false,     // a poll round on: the opossum swings
    bottomRoom: Int = 96,      // dp under the last post: the buttons floating there clear it
    topRoom: androidx.compose.ui.unit.Dp = 8.dp, // over the first post: a bar laid over the list
) {
    if (posts.isEmpty()) {
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally) {
            if (!thread) Possum(busy)
            Text(emptyText ?: stringResource(R.string.lane_empty),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            footer?.let { Spacer(Modifier.height(24.dp)); it() }
        }
        return
    }
    if (prefetch != "off") Ahead(state, posts, prefetch)
    LazyColumn(state = state, modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = if (thread) 0.dp else 8.dp,
            end = if (thread) 0.dp else 8.dp, top = topRoom, bottom = bottomRoom.dp),
        verticalArrangement = Arrangement.spacedBy(if (thread) 0.dp else 8.dp)) {
        header?.let { h -> item(key = "header") { h() } }
        // "new below" is an item of its own: it comes and goes without moving the post
        // it stands over (the list keeps its place by the first item's key on a refresh)
        posts.forEach { p ->
            divider?.takeIf { it.first == p.key }?.let { (_, words) ->
                item(key = "new-below") { NewBelow(words) }
            }
            item(key = p.key) {
                val ev = p.event
                if (ev != null) EventRow(ev, p.unread, act)  // a lane's event, among its posts
                else if (thread) ThreadRow(p, focused = p.sid == focus, act, hideSensitive)
                else PostCard(p, act, hideSensitive)
            }
        }
        footer?.let { f -> item(key = "footer") { f() } }
    }
}

/** feed.prefetch: the pictures of the next posts fetched while these are read (the
 *  windows' prefetch) — the previews, or ("all") the pictures themselves too. */
@Composable
private fun Ahead(state: LazyListState, posts: List<PostItem>, how: String) {
    val context = LocalContext.current
    val asked = remember { HashSet<String>() }
    LaunchedEffect(state, posts, how) {
        snapshotFlow { state.firstVisibleItemIndex }.collect { at ->
            val loader = coil.Coil.imageLoader(context)
            posts.drop(at).take(AHEAD).forEach { p ->
                p.media.forEach { m ->
                    val urls = listOf(m.preview) + if (how == "all" && m.kind == "image") listOf(m.url) else emptyList()
                    urls.filter { it.startsWith("https://") && asked.add(it) }.forEach { u ->
                        loader.enqueue(ImageRequest.Builder(context).data(u).build())
                    }
                }
                if (p.avatar.startsWith("https://") && asked.add(p.avatar)) {
                    loader.enqueue(ImageRequest.Builder(context).data(p.avatar).build())
                }
            }
        }
    }
}

private const val AHEAD = 12 // posts past the first on screen whose pictures come ahead

@Composable
private fun NewBelow(words: String) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        val c = MaterialTheme.colorScheme.primary
        Box(Modifier.weight(1f).height(1.dp).background(c))
        Text(words.uppercase(), color = c, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
            letterSpacing = 0.5.sp)
        Box(Modifier.weight(1f).height(1.dp).background(c))
    }
}

private val timeOnly = DateTimeFormatter.ofPattern("HH:mm")
private val dayAndTime = DateTimeFormatter.ofPattern("dd.MM HH:mm")

fun shownTime(iso: String): String = try {
    val t = OffsetDateTime.parse(iso).atZoneSameInstant(ZoneId.systemDefault())
    if (t.toLocalDate() == LocalDate.now()) t.format(timeOnly) else t.format(dayAndTime)
} catch (e: Exception) {
    ""
}

@Composable
fun Avatar(p: PostItem, size: Int) {
    val shape = CircleShape
    Box(Modifier.size(size.dp).clip(shape).background(faceColor(p.handle)),
        contentAlignment = Alignment.Center) {
        Text(p.name.take(1).uppercase(), color = Color.White, fontWeight = FontWeight.SemiBold,
            fontSize = (size * 0.42).sp)
        if (p.avatar.isNotBlank()) {
            AsyncImage(model = ImageRequest.Builder(LocalContext.current).data(p.avatar)
                .crossfade(true).build(),
                contentDescription = null, contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize())
        }
    }
}

/** A card in a lane (variant A of the mockups): face, who, when, #alias; words, pictures. */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
fun PostCard(p: PostItem, act: CardActions, hideSensitive: Boolean) {
    // a tap: its thread; a long press (anywhere but a link or a button): its menu, the ⋯
    // sheet — the phone's way to a thing's menu (Fable's review, 09.11)
    var menu by remember { mutableStateOf(false) }
    val haptic = LocalHapticFeedback.current
    val hold = remember { { haptic.performHapticFeedback(HapticFeedbackType.LongPress); menu = true } }
    val menuWords = stringResource(R.string.more)
    val surface = MaterialTheme.colorScheme.surface
    val dm = directOf(p, act)
    val dc = directColor(act)
    Surface(shape = RoundedCornerShape(12.dp),
        color = if (dm == "fill") mixed(surface, dc, 0.11f) else surface,
        border = when (dm) {
            "frame" -> androidx.compose.foundation.BorderStroke(2.dp, mixed(surface, dc, 0.75f))
            "fill" -> androidx.compose.foundation.BorderStroke(1.dp, mixed(surface, dc, 0.30f))
            else -> null
        },
        tonalElevation = 0.dp, shadowElevation = if (p.unread) 1.dp else 0.dp,
        modifier = Modifier.fillMaxWidth().combinedClickable(onLongClickLabel = menuWords,
            onLongClick = hold) { act.open(p) }) {
      CompositionLocalProvider(LocalCardHold provides hold) {
        // the face beside the head only, the words the card's whole width under it — as
        // the windows and the web page draw a card (08.11: a column beside the face left
        // a strip of nothing down the post's left side, the text narrow)
        Column(Modifier.then(if (dm == "frame") Modifier.innerGlow(dc) else Modifier)
            .padding(start = 14.dp, end = 6.dp, top = 12.dp, bottom = 2.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically) {
                val who = stringResource(R.string.profile_of, p.handle)
                Box(Modifier.clip(CircleShape).clickable(enabled = p.accountId.isNotBlank()) {
                    act.profile(p.accountId)
                }.semantics { contentDescription = who }) { Avatar(p, 36) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Head(p, act, dim = !p.unread)
                    // "♻ boosted by X · 14:02": a tap — their profile
                    val boosted = p.boosted
                    if (boosted != null) BitLine(boosted, act, html = p.boostedHtml)
                    else if (p.sharedBy.isNotBlank()) {
                        Small(stringResource(R.string.shared_by, p.sharedBy))
                    }
                    // the windows' marks (time, edited, old, bot…), each with its link (the
                    // thread, the post's edits), and, all accounts in one, whose
                    val tint = hexColor(p.viaColor)
                    MetaLine(p, act, if (tint == null) p.via else "")
                    if (tint != null && p.via.isNotBlank()) {  // whose: in that account's colour
                        Text(p.via, fontSize = 12.sp, color = Color.White,
                            modifier = Modifier.clip(RoundedCornerShape(4.dp)).background(tint)
                                .padding(horizontal = 6.dp, vertical = 1.dp))
                    }
                }
            }
            if (p.contextText.isNotBlank() && p.number == null) {
                Text("↳ @${p.contextHandle}: ${p.contextText}", maxLines = 2,
                    overflow = TextOverflow.Ellipsis, fontStyle = FontStyle.Italic,
                    fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            // the parent not here (yet): "the post it answers is gone" / "fetching…"
            val ctxLine = p.contextLine
            if (p.contextText.isBlank() && p.number == null && ctxLine != null) {
                BitLine(ctxLine, act)
            }
            // someone new in a private talk: before the words, in the warning's colour
            p.newcomer?.let { BitLine(it, act, MaterialTheme.colorScheme.error) }
            Body(p, act, hideSensitive)
            p.conversation?.let { ConversationLine(it, act) }
            p.myReplies.forEach { BitLine(it, act) }
            p.threadNews?.let { BitLine(it, act, MaterialTheme.colorScheme.primary) }
            Actions(p, act, menu) { menu = it }
        }
      }
    }
}

/** A comment in a thread: indented by depth with a thread line, its /N, smaller face. */
@Composable
fun ThreadRow(p: PostItem, focused: Boolean, act: CardActions, hideSensitive: Boolean) {
    var menu by remember { mutableStateOf(false) }
    val haptic = LocalHapticFeedback.current
    val hold = remember { { haptic.performHapticFeedback(HapticFeedbackType.LongPress); menu = true } }
    val depth = p.indent  // the model's (INDENT_MAX), as every interface draws it
    val bg = when {
        focused -> MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.55f)
        p.unread -> MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
        else -> Color.Transparent
    }
    CompositionLocalProvider(LocalCardHold provides hold) {
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min).background(bg)
        .pointerInput(p.key) { detectTapGestures(onLongPress = { hold() }) }
        .padding(start = 14.dp + (if (depth > 0) (depth - 1) * 16 else 0).dp)) {
        if (depth > 0) {
            Box(Modifier.padding(top = 4.dp, bottom = 4.dp, end = 10.dp).width(2.dp)
                .fillMaxHeight()
                .background(MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(1.dp)))
        }
        Column(Modifier.weight(1f).padding(top = 10.dp, end = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.clip(CircleShape).clickable(enabled = p.accountId.isNotBlank()) {
                    act.profile(p.accountId)
                }) { Avatar(p, 24) }
                // no weight here: the spacer's is the only one, so /N stands at the right edge
                val name = remember(p.name, p.nameHtml) { nameText(p.name, p.nameHtml) }
                Text(name, inlineContent = remember(name) { emojiContent(name) },
                    color = nickColor(p.nameColor),
                    fontWeight = if (focused) FontWeight.Bold else FontWeight.SemiBold,
                    fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.widthIn(max = 220.dp))
                Text(shownTime(p.created), fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.weight(1f))
                p.number?.let {
                    Text("/$it", fontSize = 13.sp, fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            MetaLine(p, act, p.via)
            p.newcomer?.let { BitLine(it, act, MaterialTheme.colorScheme.error) }
            Body(p, act, hideSensitive)
            Actions(p, act, menu) { menu = it }
        }
    }
    }
}

/** How this card stands out as a private message: the core's choice, for a private one. */
private fun directOf(p: PostItem, act: CardActions) =
    if (p.visibility == "direct" && !p.lanePrivate) act.directMark else "none"

/** The theme's colour of private messages; none (the phone's own look) — Fedilab's violet,
 *  for a light card or a dark one (palette.BY_VIEW, the windows'). */
@Composable
private fun directColor(act: CardActions): Color = act.directColor
    ?: if (MaterialTheme.colorScheme.surface.luminance() > 0.5f) Color(0xFF7E4CC9)
       else Color(0xFFB38CF5)

private fun mixed(a: Color, b: Color, part: Float) = Color(
    red = a.red + (b.red - a.red) * part, green = a.green + (b.green - a.green) * part,
    blue = a.blue + (b.blue - a.blue) * part, alpha = 1f)

/** A light glow in from every edge, under the card's content: the frame's inner side. */
private fun Modifier.innerGlow(c: Color) = drawBehind {
    val w = 14.dp.toPx()
    val glow = c.copy(alpha = 0.22f)
    val none = c.copy(alpha = 0f)
    drawRect(Brush.verticalGradient(listOf(glow, none), 0f, w),
        size = androidx.compose.ui.geometry.Size(size.width, w))
    drawRect(Brush.verticalGradient(listOf(none, glow), size.height - w, size.height),
        topLeft = androidx.compose.ui.geometry.Offset(0f, size.height - w),
        size = androidx.compose.ui.geometry.Size(size.width, w))
    drawRect(Brush.horizontalGradient(listOf(glow, none), 0f, w),
        size = androidx.compose.ui.geometry.Size(w, size.height))
    drawRect(Brush.horizontalGradient(listOf(none, glow), size.width - w, size.width),
        topLeft = androidx.compose.ui.geometry.Offset(size.width - w, 0f),
        size = androidx.compose.ui.geometry.Size(w, size.height))
}

@Composable
private fun Head(p: PostItem, act: CardActions, dim: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        if (p.unread) {
            Box(Modifier.padding(end = 6.dp).size(8.dp).clip(CircleShape)
                .background(MaterialTheme.colorScheme.primary))
        }
        if (directOf(p, act) == "badge") {  // the plate "DM": the terminal's, bnw's
            val dc = directColor(act)
            Text(stringResource(R.string.direct_badge), fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                color = act.onDirect ?: if (dc.luminance() > 0.45f) Color(0xFF111111) else Color.White,
                modifier = Modifier.padding(end = 6.dp).clip(RoundedCornerShape(3.dp))
                    .background(dc).padding(horizontal = 5.dp))
        }
        // the name comes first: the handle gets what's left, at most a short piece
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
            val name = remember(p.name, p.nameHtml) { nameText(p.name, p.nameHtml) }
            Text(name, inlineContent = remember(name) { emojiContent(name) },
                color = nickColor(p.nameColor),
                fontWeight = FontWeight.SemiBold, fontSize = 13.sp, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false)
                    .alpha(if (dim) 0.85f else 1f)
                    .clickable(enabled = p.accountId.isNotBlank()) { act.profile(p.accountId) })
            Spacer(Modifier.width(6.dp))
            Text("@" + p.handle.substringBefore("@"), fontSize = 13.sp, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 110.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.width(8.dp))
        Text(shownTime(p.created), fontSize = 13.sp, maxLines = 1,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (p.alias.isNotBlank()) {
            Text("#" + p.alias, fontSize = 13.sp, fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                // a tap puts it into the command line — only when there is one: off, the
                // tap did nothing (31.10), so it is plain text then
                modifier = Modifier.padding(start = 8.dp, end = 4.dp)
                    .then(if (act.aliasTaps) Modifier.clickable { act.alias(p.alias) }
                          else Modifier))
        }
    }
}

/** The card's marks (the windows' meta: its time, visibility, edited, old, bot…) in one
 *  line; one with a link (the time — the thread, "edited" — its edits) is tapped on its own. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun MetaLine(p: PostItem, act: CardActions, via: String) {
    val bits = p.meta.ifEmpty {
        if (p.labels.isNotBlank()) listOf(p.labels to "") else emptyList()
    } + (if (via.isNotBlank()) listOf(via to "") else emptyList())
    if (bits.isEmpty()) return
    androidx.compose.foundation.layout.FlowRow {
        bits.forEachIndexed { i, (words, link) ->
            Text((if (i > 0) " · " else "") + words, fontSize = 12.sp,
                color = if (link.isNotBlank()) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = if (link.isNotBlank()) Modifier.clickable { act.link(link) } else Modifier)
        }
    }
}

/** An event's row in any lane that takes events (common/activity.EventParts, the windows'
 *  row): who (each name — their profile), what · when, the post it is about (its thread),
 *  × and a request's yes / no. Every action is a fedtail: link, done as a card's links
 *  (AppModel.openLink: a person, a thread here; the rest the windows' way). Unread until
 *  seen on screen, as a post. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun EventRow(ev: EventItem, unread: Boolean, act: CardActions) {
    val ground = if (unread) MaterialTheme.colorScheme.secondaryContainer
                 else MaterialTheme.colorScheme.surface
    val text = if (unread) MaterialTheme.colorScheme.onSecondaryContainer
               else MaterialTheme.colorScheme.onSurface
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(ground)
        .clickable(enabled = ev.postLink.isNotBlank()) { act.link(ev.postLink) }
        .padding(start = 14.dp, end = 4.dp, top = 8.dp, bottom = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.Top) {
            androidx.compose.foundation.layout.FlowRow(Modifier.weight(1f).padding(top = 4.dp)) {
                if (ev.notice.isNotBlank()) {  // the server's own: what happened, not who did it
                    Text("⚠ " + ev.notice, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                        color = text)
                } else {
                    ev.people.forEachIndexed { i, (name, link) ->
                        // :blobcat: in a name: its picture (people_html), as the windows'
                        val shown = remember(name, ev.peopleHtml) {
                            nameText(name + if (i < ev.people.size - 1) ", " else "",
                                     ev.peopleHtml.getOrNull(i)?.let {
                                         if (it.isBlank()) it
                                         else it + if (i < ev.people.size - 1) ", " else ""
                                     } ?: "")
                        }
                        Text(shown, inlineContent = remember(shown) { emojiContent(shown) },
                            fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = text,
                            modifier = Modifier.clickable(enabled = link.isNotBlank()) { act.link(link) })
                    }
                    if (ev.more.isNotBlank()) Text(" " + ev.more, fontSize = 14.sp, color = text)
                }
                Text(" — " + ev.what + (if (ev.whenText.isNotBlank()) " · " + ev.whenText else ""),
                    fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (ev.hide.isNotBlank()) {
                TextButton(onClick = { act.link(ev.hide) },
                    modifier = Modifier.semantics { contentDescription = ev.hideTip }) {
                    Text("×", fontSize = 18.sp)
                }
            }
        }
        ev.answers.forEach { (yes, no) ->  // waiting for my yes: answered right here
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                listOf(yes, no).forEachIndexed { i, url ->
                    val words = ev.answerWords.getOrNull(i)?.first.orEmpty()
                    TextButton(onClick = { act.link(url) }) {
                        Text(words, fontWeight = if (i == 0) FontWeight.SemiBold else FontWeight.Normal)
                    }
                }
            }
        }
        if (ev.post.isNotBlank()) {
            Text(ev.post, fontSize = 13.sp, maxLines = 3, overflow = TextOverflow.Ellipsis,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(end = 10.dp))
        }
    }
}

/** A line around a card (common/cardtext.py): its words, a tap on it — its link (a thread,
 *  a person). */
@Composable
private fun BitLine(bit: Pair<String, String>, act: CardActions, color: Color? = null,
                    html: String = "") {
    // with a name's :emoji: (the core's html): their pictures, as in the card's head
    val words = remember(bit.first, html) { nameText(bit.first, html) }
    Text(words, inlineContent = remember(words) { emojiContent(words) },
        fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
        color = color ?: MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.fillMaxWidth()
            .clickable(enabled = bit.second.isNotBlank()) { act.link(bit.second) }
            .padding(vertical = 2.dp))
}

/** A thread card's line ("14 comments · 1 new · bob: …"), opening with the theme's own
 *  "thread" picture, as in the windows — not an emoji a font may lack. */
@Composable
private fun ConversationLine(bit: Pair<String, String>, act: CardActions) {
    val grey = MaterialTheme.colorScheme.onSurfaceVariant
    Row(verticalAlignment = Alignment.CenterVertically) {
        ThemedIcon("thread", Glyphs.Thread, null, Modifier.size(14.dp), tint = grey)
        Spacer(Modifier.width(4.dp))
        Box(Modifier.weight(1f)) { BitLine(bit, act) }
    }
}

@Composable
private fun Small(text: String) {
    Text(text, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/** The words (behind a warning, if any), pictures, a poll, a link's card. */
@Composable
private fun Body(p: PostItem, act: CardActions, hideSensitive: Boolean) {
    // folded by its own warning, or by a server filter that says "warn" (expanding every
    // warning doesn't open those: the filter is the reader's own)
    val folded = p.warning.isNotBlank() || p.foldedBy.isNotBlank()
    var open by rememberSaveable(p.key, act.expandCw) {
        mutableStateOf(!folded || (act.expandCw && p.foldedBy.isBlank()))
    }
    if (folded) {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .clickable { open = !open }.padding(horizontal = 10.dp, vertical = 8.dp)) {
            Text(listOf(p.foldedBy, if (p.warning.isNotBlank()) "⚠ " + p.warning else "")
                    .filter { it.isNotBlank() }.joinToString(" · "),
                fontSize = 14.sp, fontWeight = FontWeight.Medium,
                modifier = Modifier.weight(1f))
            Text(stringResource(if (open) R.string.cw_hide else R.string.cw_show), fontSize = 13.sp,
                color = MaterialTheme.colorScheme.primary)
        }
    }
    if (!open) return
    if (p.text.isNotBlank()) {
        val color = MaterialTheme.colorScheme.primary
        val words = remember(p.html, p.text, color) { postText(p.html, p.text, color) }
        PostWords(words, act.link, act.runLink, act.tagMenu, act.holdSelects) { act.open(p) }
    }
    if (p.media.isNotEmpty()) {
        MediaGrid(p.media, blurred = hideSensitive && p.sensitive,
            menu = act.mediaMenu?.let { f -> val m: suspend (Int) -> JSONArray = { i -> f(p, i) }; m },
            browser = act.browser) { i -> act.media(p.media, i) }
    }
    if (p.pollOpen && p.pollOptions.isNotEmpty()) {
        Vote(p, act)
    } else if (p.pollOptions.isNotEmpty() && p.pollShares.size == p.pollOptions.size) {
        PollResults(p, act)
    } else if (p.poll.isNotBlank()) {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant).padding(start = 10.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text(p.poll, fontSize = 14.sp, modifier = Modifier.weight(1f).padding(vertical = 10.dp))
            IconButton(onClick = { act.pollRefresh(p) }) {   // fresh counts
                ThemedIcon("refresh", androidx.compose.material.icons.Icons.Filled.Refresh,
                    stringResource(R.string.refresh), Modifier.size(18.dp))
            }
        }
    }
    if (p.reactions.isNotBlank()) Small(p.reactions)
    val quoteLine = p.quoteLine
    if (!p.quoteOff && p.quoteWho.isBlank() && quoteLine != null) {
        // not shown (pending, revoked, blocked…): why, and where one may, "show anyway"
        Text(quoteLine.first, fontSize = 13.sp,
            color = if (quoteLine.second.isNotBlank()) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))
                .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(10.dp))
                .clickable(enabled = quoteLine.second.isNotBlank()) { act.link(quoteLine.second) }
                .padding(10.dp))
    } else if (!p.quoteOff && p.quoteText.isNotBlank()) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(10.dp))
            .clickable(enabled = p.quoteWho.isNotBlank()) { act.open(p.copy(sid = p.quoteId)) }
            .padding(10.dp)) {
            if (p.quoteWho.isNotBlank()) {
                val who = remember(p.quoteWho, p.quoteWhoHtml) {
                    nameText("❝ " + p.quoteWho,
                             if (p.quoteWhoHtml.isBlank()) "" else "❝ " + p.quoteWhoHtml)
                }
                Text(who, inlineContent = remember(who) { emojiContent(who) }, fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold)
            }
            Text(p.quoteText, fontSize = 14.sp, maxLines = 6, overflow = TextOverflow.Ellipsis,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            // it quotes too: a line, as Mastodon's page (common/cardtext.inner_quote_bit)
            p.quoteInner?.let { (text, url) ->
                Text(text, fontSize = 13.sp, color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.clickable { act.link(url) })
            }
        }
    }
    p.card?.takeIf { it.url.isNotBlank() && it.title.isNotBlank() }?.let { c -> Link(c, act) }
}

/** A poll's results: a bar per option, its share, ✓ by mine; how many people and until
 *  when under them, and ⟳ for fresh counts (the windows' footer). */
@Composable
private fun PollResults(p: PostItem, act: CardActions) {
    val top = p.pollShares.maxOrNull() ?: 0
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
        .background(MaterialTheme.colorScheme.surfaceVariant).padding(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        p.pollOptions.forEachIndexed { i, title ->
            val share = p.pollShares[i]
            val lead = share == top && top > 0
            Box(Modifier.fillMaxWidth().heightIn(min = 32.dp).clip(RoundedCornerShape(6.dp))
                .background(MaterialTheme.colorScheme.surface)) {
                Box(Modifier.matchParentSize()) {  // the bar: the option's share of the width
                    Box(Modifier.fillMaxHeight().fillMaxWidth(share.coerceIn(0, 100) / 100f)
                        .background(if (lead) MaterialTheme.colorScheme.primaryContainer
                                    else MaterialTheme.colorScheme.secondaryContainer))
                }
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text((if (i in p.pollMine) "✓ " else "") + title, fontSize = 14.sp,
                        fontWeight = if (lead) FontWeight.SemiBold else FontWeight.Normal,
                        modifier = Modifier.weight(1f))
                    Text("$share%", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(p.pollSummary, fontSize = 12.sp, modifier = Modifier.weight(1f),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            IconButton(onClick = { act.pollRefresh(p) }, modifier = Modifier.size(32.dp)) {
                ThemedIcon("refresh", androidx.compose.material.icons.Icons.Filled.Refresh,
                    stringResource(R.string.refresh), Modifier.size(18.dp))
            }
        }
    }
}

/** A poll still open: its options to tick (one, or several), then "vote". */
@Composable
private fun Vote(p: PostItem, act: CardActions) {
    var picked by remember(p.key) { mutableStateOf(setOf<Int>()) }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
        .background(MaterialTheme.colorScheme.surfaceVariant).padding(6.dp)) {
        p.pollOptions.forEachIndexed { i, title ->
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(i in picked,
                role = if (p.pollMultiple) Role.Checkbox else Role.RadioButton) {
                picked = if (p.pollMultiple) (if (i in picked) picked - i else picked + i) else setOf(i)
            }, verticalAlignment = Alignment.CenterVertically) {
                if (p.pollMultiple) Checkbox(checked = i in picked, onCheckedChange = null)
                else RadioButton(selected = i in picked, onClick = null)
                Text(title, fontSize = 14.sp, modifier = Modifier.padding(start = 8.dp, top = 8.dp, bottom = 8.dp))
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { act.vote(p, picked.sorted()) }, enabled = picked.isNotEmpty()) {
                Text(stringResource(R.string.poll_vote))
            }
            p.poll.lines().lastOrNull()?.takeIf { it.isNotBlank() && "%" !in it }?.let { Small(it) }
        }
    }
}

@Composable
private fun Link(c: LinkCard, act: CardActions) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))
        .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(10.dp))
        .clickable { act.link(c.url) }, verticalAlignment = Alignment.CenterVertically) {
        if (c.image.isNotBlank()) {
            AsyncImage(model = c.image, contentDescription = null, contentScale = ContentScale.Crop,
                modifier = Modifier.size(64.dp))
        }
        Column(Modifier.padding(10.dp).weight(1f)) {
            Text(c.title, fontSize = 14.sp, fontWeight = FontWeight.Medium, maxLines = 2,
                overflow = TextOverflow.Ellipsis)
            if (c.description.isNotBlank()) {
                Text(c.description, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (c.provider.isNotBlank()) Small(c.provider)
        }
    }
}

/** One picture wide, by its own proportions (within reason); more — two per row, square. */
@Composable
fun MediaGrid(media: List<MediaItem>, blurred: Boolean,
              menu: (suspend (Int) -> JSONArray)? = null, browser: (String) -> Unit = {},
              open: (Int) -> Unit) {
    var shown by remember(media) { mutableStateOf(!blurred) }
    val tap: (Int) -> Unit = { i -> if (shown) open(i) else { shown = true } }
    // a long press on a shown picture: its menu (hidden — the card's, as before)
    var items by remember(media) { mutableStateOf<JSONArray?>(null) }
    val scope = rememberCoroutineScope()
    val hold: ((Int) -> Unit)? = if (menu != null && shown) { i ->
        scope.launch { items = runCatching { menu(i) }.getOrNull()?.takeIf { it.length() > 0 } }
    } else null
    Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))) {
        if (media.size == 1) {
            val m = media[0]
            val ratio = if (m.w > 0 && m.h > 0) (m.w.toFloat() / m.h).coerceIn(0.66f, 2.2f) else 1.6f
            Tile(m, Modifier.fillMaxWidth().aspectRatio(ratio), shown, hold?.let { { it(0) } }) { tap(0) }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                media.take(4).chunked(2).forEachIndexed { row, pair ->
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        pair.forEachIndexed { col, m ->
                            val i = row * 2 + col
                            Tile(m, Modifier.weight(1f).aspectRatio(1f), shown, hold?.let { { it(i) } }) { tap(i) }
                        }
                        if (pair.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
            }
        }
        MediaMenu(items, browser) { items = null }
        if (!shown) {
            Text(stringResource(R.string.media_sensitive), color = Color.White, fontSize = 14.sp,
                fontWeight = FontWeight.Medium, modifier = Modifier.align(Alignment.Center)
                    .clip(RoundedCornerShape(8.dp)).background(Color(0x99000000))
                    .padding(horizontal = 12.dp, vertical = 8.dp))
        }
    }
}

/** A picture's menu (common/actions.media_items): save it, open it, copy its link, look it
 *  up in the image searches (media.image_search). */
@Composable
private fun MediaMenu(items: JSONArray?, browser: (String) -> Unit, close: () -> Unit) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val saving = stringResource(R.string.saving)
    DropdownMenu(expanded = items != null, onDismissRequest = close) {
        val list = items ?: JSONArray()
        for (k in 0 until list.length()) {
            val it = list.getJSONObject(k)
            if (it.optString("kind") == "separator") { HorizontalDivider(); continue }
            DropdownMenuItem(text = { Text(it.optString("label")) }, onClick = {
                close()
                when (it.optString("kind")) {
                    "save" -> {
                        saveMedia(context, it.optString("url"))
                        android.widget.Toast.makeText(context, saving, android.widget.Toast.LENGTH_SHORT).show()
                    }
                    "copy" -> clipboard.setText(AnnotatedString(it.optString("text")))
                    else -> browser(it.optString("url"))
                }
            })
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun Tile(m: MediaItem, modifier: Modifier, shown: Boolean, hold: (() -> Unit)? = null,
                 onClick: () -> Unit) {
    val menuWords = stringResource(R.string.media_menu)
    val haptic = LocalHapticFeedback.current
    Box(modifier.background(MaterialTheme.colorScheme.surfaceVariant).then(
            if (hold == null) Modifier.clickable(onClick = onClick)
            else Modifier.combinedClickable(onLongClickLabel = menuWords, onLongClick = {
                haptic.performHapticFeedback(androidx.compose.ui.hapticfeedback.HapticFeedbackType.LongPress)
                hold()
            }, onClick = onClick)),
        contentAlignment = Alignment.Center) {
        // a screen reader says what it is: the description, or the kind "without a description"
        val kind = stringResource(when (m.kind) {
            "video" -> R.string.kind_video
            "gifv" -> R.string.kind_gifv
            "audio" -> R.string.kind_audio
            else -> R.string.kind_image
        })
        val said = m.alt.ifBlank { stringResource(R.string.media_no_alt, kind) }
        // hidden: blurred on Android 12+; Android 11 can't blur (Modifier.blur does nothing
        // there — the picture would show), so there it isn't drawn at all: a plain tile
        // under the "sensitive" plaque until tapped
        if (shown || android.os.Build.VERSION.SDK_INT >= 31) {
            AsyncImage(model = ImageRequest.Builder(LocalContext.current)
                .data(m.preview.ifBlank { m.url }).crossfade(true).build(),
                contentDescription = said, contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize().then(if (shown) Modifier else Modifier.blur(28.dp)))
        } else {
            Box(Modifier.fillMaxSize().semantics { contentDescription = said })
        }
        if (m.kind == "video" || m.kind == "gifv" || m.kind == "audio") {
            Box(Modifier.size(48.dp).clip(CircleShape).background(Color(0x99000000)),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.PlayArrow, null, tint = Color.White)
            }
        }
        if (m.alt.isNotBlank() && shown) {
            Text("ALT", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.align(Alignment.BottomStart).padding(6.dp)
                    .clip(RoundedCornerShape(4.dp)).background(Color(0x99000000))
                    .padding(horizontal = 4.dp, vertical = 1.dp))
        }
    }
}

@Composable
private fun Actions(p: PostItem, act: CardActions, menu: Boolean, setMenu: (Boolean) -> Unit) {
    val grey = MaterialTheme.colorScheme.onSurfaceVariant
    Row(Modifier.padding(start = 0.dp), verticalAlignment = Alignment.CenterVertically) {
        TextButton(onClick = { act.reply(p) }, contentPadding = PaddingValues(horizontal = 8.dp)) {
            ThemedIcon("reply", Glyphs.Reply, stringResource(R.string.reply), Modifier.size(18.dp), tint = grey)
            if (p.replies > 0) Text(" ${p.replies}", fontSize = 13.sp, color = grey)
        }
        // a button, as ↩ and ★ beside it: a bare count let the tap through to the card,
        // which opened the thread instead (31.10); boosted — lit, a tap takes it back
        // only where the server takes a boost (common/actions.can_boost): public posts
        if (p.canBoost) TextButton(onClick = { act.share(p) },
            contentPadding = PaddingValues(horizontal = 8.dp)) {
            val lit = if (p.shared) MaterialTheme.colorScheme.secondary else grey
            ThemedIcon("boost", Glyphs.Boost,
                stringResource(if (p.shared) R.string.unboost else R.string.boost),
                Modifier.size(18.dp), tint = lit)
            if (p.shares > 0) Text(" ${p.shares}", fontSize = 13.sp, color = lit)
        }
        TextButton(onClick = { act.like(p) }, contentPadding = PaddingValues(horizontal = 8.dp)) {
            ThemedIcon(if (p.liked) "liked" else "like",
                if (p.liked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                stringResource(if (p.liked) R.string.unlike else R.string.like), Modifier.size(18.dp),
                tint = if (p.liked) MaterialTheme.colorScheme.secondary else grey)
            if (p.likes > 0) Text(" ${p.likes}", fontSize = 13.sp, color = grey)
        }
        if (act.bookmarkButton) TextButton(onClick = { act.bookmark(p) },
            contentPadding = PaddingValues(horizontal = 8.dp)) {
            val said = stringResource(if (p.bookmarked) R.string.unbookmark else R.string.bookmark)
            ThemedIcon("bookmark", if (p.bookmarked) Glyphs.Bookmarked else Glyphs.Bookmark, said,
                Modifier.size(18.dp),
                tint = if (p.bookmarked) MaterialTheme.colorScheme.secondary else grey)
        }
        Spacer(Modifier.weight(1f))
        CardMenu(p, act, menu, setMenu)
    }
}

/** A card's ⋯ (09.11, the mockup "Menu"): a sheet from the bottom — on top a grid of
 *  its tools (reply; the windows' tools over a post: open, copy the link, translate,
 *  quote, reply quoting, follow / mute the thread (lit when on), read up to here, edit,
 *  delete — common/actions.tools; the phone's share; boost), then the author's profile
 *  and the rest of the windows' menu, "Author ▸", "Thread ▸", "More ▸" opening in place. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CardMenu(p: PostItem, act: CardActions, open: Boolean, setOpen: (Boolean) -> Unit) {
    var info by remember { mutableStateOf<JSONObject?>(null) }
    // asked anew at each opening (last time's items stand till the answer: clearing them
    // first made the UI test of this menu fail on CI's slow emulator, 31.10)
    LaunchedEffect(open) { if (open) info = (act.menu ?: act.info)(p) }
    IconButton(onClick = { setOpen(true) }, modifier = Modifier.size(48.dp)) {
        ThemedIcon("more", Icons.Filled.MoreVert, stringResource(R.string.more),
            tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (open) ModalBottomSheet(onDismissRequest = { setOpen(false) }) {
        PostSheet(p, act, info) { setOpen(false) }
    }
}

/** One cell of the sheet's grid: a picture and its words (two lines at most). */
@Composable
private fun SheetTool(word: String, picture: String, fallback: ImageVector, on: Boolean = false,
                      onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().heightIn(min = 76.dp).clip(RoundedCornerShape(12.dp))
        .background(if (on) MaterialTheme.colorScheme.secondaryContainer
                    else MaterialTheme.colorScheme.surfaceVariant)
        .clickable(onClick = onClick)
        .semantics(mergeDescendants = true) { contentDescription = word; role = Role.Button; selected = on }
        .padding(horizontal = 4.dp, vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterVertically)) {
        ThemedIcon(picture, fallback, null, Modifier.size(24.dp),
            tint = if (on) MaterialTheme.colorScheme.onSecondaryContainer
                   else MaterialTheme.colorScheme.onSurface)
        Text(word, fontSize = 12.sp, lineHeight = 14.sp, maxLines = 2, textAlign = TextAlign.Center,
            overflow = TextOverflow.Ellipsis,
            color = if (on) MaterialTheme.colorScheme.onSecondaryContainer
                    else MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
private fun PostSheet(p: PostItem, act: CardActions, info: JSONObject?, close: () -> Unit) {
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    val shareWords = stringResource(R.string.share)
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
        .padding(start = 12.dp, end = 12.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp)) {
        // the grid: the reply, the tools the core offers this post now, share, boost
        val cells = mutableListOf<@Composable () -> Unit>()
        cells += { SheetTool(stringResource(R.string.reply), "reply", Glyphs.Reply) {
            close(); act.reply(p) } }
        val tools = info?.optJSONArray("tools")
        if (tools != null) for (i in 0 until tools.length()) {
            val t = tools.getJSONObject(i)
            cells += { SheetTool(t.optString("label"), "tool." + t.optString("picture"),
                Glyphs.Grid, on = t.optBoolean("on")) { close(); runItem(t, p, act, clipboard) } }
        }
        if (p.url.isNotBlank()) cells += { SheetTool(shareWords, "share", Icons.Filled.Share) {
            close()
            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                type = "text/plain"; putExtra(android.content.Intent.EXTRA_TEXT, p.url)
            }
            context.startActivity(android.content.Intent.createChooser(send, shareWords))
        } }
        if (p.canBoost) cells += { SheetTool(stringResource(if (p.shared) R.string.unboost
                                                            else R.string.boost),
            "boost", Glyphs.Boost, on = p.shared) { close(); act.share(p) } }
        cells.chunked(4).forEach { row ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                row.forEach { cell -> Box(Modifier.weight(1f)) { cell() } }
                repeat(4 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
        HorizontalDivider(Modifier.padding(vertical = 6.dp))
        if (p.accountId.isNotBlank()) SheetLine(stringResource(R.string.profile_of, p.handle)) {
            close(); act.profile(p.accountId)
        }
        val items = info?.optJSONArray("items")
        if (items == null) {  // the windows' menu on its way (or failed): the short one
            SheetLine(stringResource(if (p.bookmarked) R.string.unbookmark else R.string.bookmark)) {
                close(); act.bookmark(p)
            }
        } else SheetItems(items, p, act, close, clipboard)
    }
}

/** The menu's lines as the windows have them; a submenu opens in place. */
@Composable
private fun SheetItems(items: org.json.JSONArray, p: PostItem, act: CardActions, close: () -> Unit,
                       clipboard: androidx.compose.ui.platform.ClipboardManager, depth: Int = 0) {
    for (i in 0 until items.length()) {
        val item = items.getJSONObject(i)
        val label = item.optString("label")
        when (item.optString("kind")) {
            "separator" -> HorizontalDivider(Modifier.padding(vertical = 4.dp))
            "submenu" -> {
                var unfolded by remember(label) { mutableStateOf(false) }
                SheetLine(label, trailing = if (unfolded) "▾" else "▸") { unfolded = !unfolded }
                if (unfolded) Column(Modifier.padding(start = 16.dp)) {
                    SheetItems(item.optJSONArray("items") ?: org.json.JSONArray(), p, act, close,
                        clipboard, depth + 1)
                }
            }
            // all accounts in one: ★ ♻ ↩ as another of them, one line a choice
            "act_as" -> {
                val cs = item.optJSONArray("choices") ?: org.json.JSONArray()
                for (k in 0 until cs.length()) {
                    val c = cs.getJSONObject(k)
                    SheetLine(c.optString("label")) {
                        close(); act.actAs(p, c.optString("tag"), c.optString("action"))
                    }
                }
            }
            "quote_reply" -> SheetLine("❝ $label") { close(); act.quoteReply(p) }
            else -> SheetLine(if (item.optJSONObject("page") != null) "$label …" else label) {
                close(); runItem(item, p, act, clipboard)
            }
        }
    }
}

@Composable
private fun SheetLine(words: String, trailing: String = "", onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clip(RoundedCornerShape(8.dp))
        .clickable(onClick = onClick).padding(horizontal = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(words, fontSize = 15.sp, modifier = Modifier.weight(1f))
        if (trailing.isNotBlank()) Text(trailing, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** An item of the menu (or a tool) done: the windows' kinds (common/actions.Item). */
private fun runItem(item: JSONObject, p: PostItem, act: CardActions,
                    clipboard: androidx.compose.ui.platform.ClipboardManager) {
    when (item.optString("kind")) {
        "link" -> act.runLink(item.optString("url"))
        "open" -> act.browser(item.optString("url"))
        "copy" -> clipboard.setText(AnnotatedString(item.optString("text")))
        "quote_reply" -> act.quoteReply(p)
        else -> item.optJSONObject("page")?.let { pg -> act.page(pg.optString("page"), pg.optString("arg")) }
    }
}

/** people.nick_colors: "#rrggbb" → its colour; "" — the text's own. */
internal fun nickColor(hex: String): Color =
    if (hex.length == 7 && hex.startsWith("#"))
        hex.substring(1).toLongOrNull(16)?.let { Color(0xFF000000 or it) } ?: Color.Unspecified
    else Color.Unspecified
