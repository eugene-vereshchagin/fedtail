package online.dmesg.fedtail

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
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import kotlinx.coroutines.delay
import org.json.JSONObject
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

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
    val page: (String, String) -> Unit = { _, _ -> }, // a place of that menu (lists, translate…)
    val quoteReply: (PostItem) -> Unit = {},
    val vote: (PostItem, List<Int>) -> Unit = { _, _ -> },
)

fun AppModel.cardActions(openBrowser: (String) -> Unit) = CardActions(
    open = { openThread(it.sid) }, reply = { compose(it) }, like = { act(it, "like") },
    media = { list, i -> openMedia(list, i) }, link = { openLink(it, openBrowser) },
    alias = { putAlias(it) }, share = { act(it, "share") }, bookmark = { act(it, "bookmark") },
    info = { menuOf(it) }, thread = { p, what -> threadAct(p, what) }, browser = openBrowser,
    expandCw = expandCw, profile = { openProfile(it) }, menu = { postMenu(it) },
    runLink = { runLink(it) }, page = { name, arg -> openPage(name, arg) },
    quoteReply = { quoteReply(it) }, vote = { p, choices -> vote(p, choices) })

private val EMOJI = Regex("""<img\b[^>]*\balt="([^"]*)"[^>]*>""")

/** A post's HTML as text, its links coloured and marked "URL" (custom emoji as their
 *  :code: for now). Plain marks, not Compose's own link handling: that takes every tap
 *  on the text, and a tap beside a link must open the thread (PostWords decides). */
fun postText(html: String, plain: String, linkColor: Color): AnnotatedString {
    if (html.isBlank()) return AnnotatedString(plain)
    return try {
        val a = AnnotatedString.fromHtml(EMOJI.replace(html) { it.groupValues[1] })
        var end = a.length
        while (end > 0 && a[end - 1].isWhitespace()) end--
        buildAnnotatedString {
            append(a.text.substring(0, end))
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

/** A post's words: a tap on a link follows it, a tap anywhere else is the card's own. */
@Composable
private fun PostWords(words: AnnotatedString, onLink: (String) -> Unit, onTap: () -> Unit) {
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    val link by rememberUpdatedState(onLink)
    val tap by rememberUpdatedState(onTap)
    Text(words, fontSize = 15.sp, lineHeight = 21.sp, onTextLayout = { layout = it },
        modifier = Modifier.pointerInput(words) {
            detectTapGestures { pos ->
                val at = layout?.getOffsetForPosition(pos)
                val url = at?.let { words.getStringAnnotations("URL", it, it).firstOrNull()?.item }
                if (url != null) link(url) else tap()
            }
        })
}

/** Read marks: what stood whole on screen when scrolling stopped (read.mark_read). */
@Composable
fun MarkWhileScrolling(state: LazyListState, on: Boolean, mark: (List<String>) -> Unit) {
    LaunchedEffect(state, on) {
        if (!on) return@LaunchedEffect
        snapshotFlow { state.isScrollInProgress to state.layoutInfo.visibleItemsInfo.size }
            .collect { (scrolling, _) ->
                if (scrolling) return@collect
                delay(350)
                val info = state.layoutInfo
                mark(info.visibleItemsInfo.filter {
                    it.offset >= info.viewportStartOffset &&
                        it.offset + it.size <= info.viewportEndOffset
                }.mapNotNull { it.key as? String })
            }
    }
}

/** A lane opened anew stands on its first unread post, like the desktop; never jumps after. */
suspend fun aim(state: LazyListState, posts: List<PostItem>, newestFirst: Boolean, before: Int = 0,
                divider: String? = null) {
    if (posts.isEmpty()) return
    val firstUnread = posts.indexOfFirst { it.unread }
    val at = when {
        firstUnread >= 0 -> firstUnread
        newestFirst -> 0
        else -> posts.size - 1
    }
    // before: items the list holds ahead of the posts ("earlier" at the top); "new below"
    // is an item too: one more ahead of every post from it on — and it is shown itself
    val line = divider?.let { d -> posts.indexOfFirst { it.key == d } } ?: -1
    state.scrollToItem(before + at + if (line in 0..at) (if (line == at) 0 else 1) else 0)
}

@Composable
fun PostList(
    posts: List<PostItem>, state: LazyListState, divider: Pair<String, String>?,
    act: CardActions, hideSensitive: Boolean, thread: Boolean = false, focus: String? = null,
    footer: (@Composable () -> Unit)? = null,
    header: (@Composable () -> Unit)? = null,
) {
    if (posts.isEmpty()) {
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally) {
            Text(stringResource(R.string.lane_empty),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            footer?.let { Spacer(Modifier.height(24.dp)); it() }
        }
        return
    }
    LazyColumn(state = state, modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = if (thread) 0.dp else 8.dp,
            end = if (thread) 0.dp else 8.dp, top = 8.dp, bottom = 96.dp),
        verticalArrangement = Arrangement.spacedBy(if (thread) 0.dp else 8.dp)) {
        header?.let { h -> item(key = "header") { h() } }
        // "new below" is an item of its own: it comes and goes without moving the post
        // it stands over (the list keeps its place by the first item's key on a refresh)
        posts.forEach { p ->
            divider?.takeIf { it.first == p.key }?.let { (_, words) ->
                item(key = "new-below") { NewBelow(words) }
            }
            item(key = p.key) {
                if (thread) ThreadRow(p, focused = p.sid == focus, act, hideSensitive)
                else PostCard(p, act, hideSensitive)
            }
        }
        footer?.let { f -> item(key = "footer") { f() } }
    }
}

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
@Composable
fun PostCard(p: PostItem, act: CardActions, hideSensitive: Boolean) {
    Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp, shadowElevation = if (p.unread) 1.dp else 0.dp,
        modifier = Modifier.fillMaxWidth().clickable { act.open(p) }) {
        Row(Modifier.padding(start = 14.dp, end = 6.dp, top = 12.dp, bottom = 2.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.clip(CircleShape).clickable(enabled = p.accountId.isNotBlank()) {
                act.profile(p.accountId)
            }) { Avatar(p, 36) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Head(p, act, dim = !p.unread)
                if (p.sharedBy.isNotBlank()) {
                    Small(stringResource(R.string.shared_by, p.sharedBy))
                }
                if (p.contextText.isNotBlank() && p.number == null) {
                    Text("↳ @${p.contextHandle}: ${p.contextText}", maxLines = 2,
                        overflow = TextOverflow.Ellipsis, fontStyle = FontStyle.Italic,
                        fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Body(p, act, hideSensitive)
                Actions(p, act)
            }
        }
    }
}

/** A comment in a thread: indented by depth with a thread line, its /N, smaller face. */
@Composable
fun ThreadRow(p: PostItem, focused: Boolean, act: CardActions, hideSensitive: Boolean) {
    val depth = minOf(p.depth, 6)
    val bg = when {
        focused -> MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.55f)
        p.unread -> MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
        else -> Color.Transparent
    }
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min).background(bg)
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
                Text(p.name, fontWeight = if (focused) FontWeight.Bold else FontWeight.SemiBold,
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
            Body(p, act, hideSensitive)
            Actions(p, act)
        }
    }
}

@Composable
private fun Head(p: PostItem, act: CardActions, dim: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        if (p.unread) {
            Box(Modifier.padding(end = 6.dp).size(8.dp).clip(CircleShape)
                .background(MaterialTheme.colorScheme.primary))
        }
        // the name comes first: the handle gets what's left, at most a short piece
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
            Text(p.name, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, maxLines = 1,
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
                modifier = Modifier.padding(start = 8.dp, end = 4.dp)
                    .clickable { act.alias(p.alias) })
        }
    }
}

@Composable
private fun Small(text: String) {
    Text(text, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/** The words (behind a warning, if any), pictures, a poll, a link's card. */
@Composable
private fun Body(p: PostItem, act: CardActions, hideSensitive: Boolean) {
    var open by rememberSaveable(p.key, act.expandCw) {
        mutableStateOf(p.warning.isBlank() || act.expandCw)
    }
    if (p.warning.isNotBlank()) {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .clickable { open = !open }.padding(horizontal = 10.dp, vertical = 8.dp)) {
            Text("⚠ " + p.warning, fontSize = 14.sp, fontWeight = FontWeight.Medium,
                modifier = Modifier.weight(1f))
            Text(stringResource(if (open) R.string.cw_hide else R.string.cw_show), fontSize = 13.sp,
                color = MaterialTheme.colorScheme.primary)
        }
    }
    if (!open) return
    if (p.text.isNotBlank()) {
        val color = MaterialTheme.colorScheme.primary
        val words = remember(p.html, p.text, color) { postText(p.html, p.text, color) }
        PostWords(words, act.link) { act.open(p) }
    }
    if (p.media.isNotEmpty()) {
        MediaGrid(p.media, blurred = hideSensitive && p.sensitive) { i -> act.media(p.media, i) }
    }
    if (p.pollOpen && p.pollOptions.isNotEmpty()) {
        Vote(p, act)
    } else if (p.poll.isNotBlank()) {
        Text(p.poll, fontSize = 14.sp, modifier = Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(8.dp)).background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(10.dp))
    }
    if (p.quoteText.isNotBlank()) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(10.dp))
            .clickable(enabled = p.quoteWho.isNotBlank()) { act.open(p.copy(sid = p.quoteId)) }
            .padding(10.dp)) {
            if (p.quoteWho.isNotBlank()) Text("❝ " + p.quoteWho, fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold)
            Text(p.quoteText, fontSize = 14.sp, maxLines = 6, overflow = TextOverflow.Ellipsis,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    p.card?.takeIf { it.url.isNotBlank() && it.title.isNotBlank() }?.let { c -> Link(c, act) }
}

/** A poll still open: its options to tick (one, or several), then "vote". */
@Composable
private fun Vote(p: PostItem, act: CardActions) {
    var picked by remember(p.key) { mutableStateOf(setOf<Int>()) }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
        .background(MaterialTheme.colorScheme.surfaceVariant).padding(6.dp)) {
        p.pollOptions.forEachIndexed { i, title ->
            Row(Modifier.fillMaxWidth().clickable {
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
            if (c.provider.isNotBlank()) Small(c.provider)
        }
    }
}

/** One picture wide, by its own proportions (within reason); more — two per row, square. */
@Composable
fun MediaGrid(media: List<MediaItem>, blurred: Boolean, open: (Int) -> Unit) {
    var shown by remember(media) { mutableStateOf(!blurred) }
    val tap: (Int) -> Unit = { i -> if (shown) open(i) else { shown = true } }
    Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))) {
        if (media.size == 1) {
            val m = media[0]
            val ratio = if (m.w > 0 && m.h > 0) (m.w.toFloat() / m.h).coerceIn(0.66f, 2.2f) else 1.6f
            Tile(m, Modifier.fillMaxWidth().aspectRatio(ratio), shown) { tap(0) }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                media.take(4).chunked(2).forEachIndexed { row, pair ->
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        pair.forEachIndexed { col, m ->
                            val i = row * 2 + col
                            Tile(m, Modifier.weight(1f).aspectRatio(1f), shown) { tap(i) }
                        }
                        if (pair.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
            }
        }
        if (!shown) {
            Text(stringResource(R.string.media_sensitive), color = Color.White, fontSize = 14.sp,
                fontWeight = FontWeight.Medium, modifier = Modifier.align(Alignment.Center)
                    .clip(RoundedCornerShape(8.dp)).background(Color(0x99000000))
                    .padding(horizontal = 12.dp, vertical = 8.dp))
        }
    }
}

@Composable
private fun Tile(m: MediaItem, modifier: Modifier, shown: Boolean, onClick: () -> Unit) {
    Box(modifier.background(MaterialTheme.colorScheme.surfaceVariant).clickable(onClick = onClick),
        contentAlignment = Alignment.Center) {
        AsyncImage(model = ImageRequest.Builder(LocalContext.current)
            .data(m.preview.ifBlank { m.url }).crossfade(true).build(),
            contentDescription = m.alt.ifBlank { null }, contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize().then(if (shown) Modifier else Modifier.blur(28.dp)))
        if (m.kind == "video" || m.kind == "gifv" || m.kind == "audio") {
            Box(Modifier.size(48.dp).clip(CircleShape).background(Color(0x99000000)),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.PlayArrow, null, tint = Color.White)
            }
        }
        if (m.alt.isNotBlank() && shown) {
            Text("ALT", color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.align(Alignment.BottomStart).padding(6.dp)
                    .clip(RoundedCornerShape(4.dp)).background(Color(0x99000000))
                    .padding(horizontal = 4.dp, vertical = 1.dp))
        }
    }
}

@Composable
private fun Actions(p: PostItem, act: CardActions) {
    val grey = MaterialTheme.colorScheme.onSurfaceVariant
    Row(Modifier.padding(start = 0.dp), verticalAlignment = Alignment.CenterVertically) {
        TextButton(onClick = { act.reply(p) }, contentPadding = PaddingValues(horizontal = 8.dp)) {
            Icon(Glyphs.Reply, stringResource(R.string.reply), Modifier.size(18.dp), tint = grey)
            if (p.replies > 0) Text(" ${p.replies}", fontSize = 13.sp, color = grey)
        }
        Row(Modifier.padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Glyphs.Boost, null, Modifier.size(18.dp), tint = grey)
            if (p.shares > 0) Text(" ${p.shares}", fontSize = 13.sp, color = grey)
        }
        TextButton(onClick = { act.like(p) }, contentPadding = PaddingValues(horizontal = 8.dp)) {
            Icon(if (p.liked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                stringResource(R.string.like), Modifier.size(18.dp),
                tint = if (p.liked) MaterialTheme.colorScheme.secondary else grey)
            if (p.likes > 0) Text(" ${p.likes}", fontSize = 13.sp, color = grey)
        }
        Spacer(Modifier.weight(1f))
        CardMenu(p, act)
    }
}

/** A card's ⋯: boost and bookmark first, then the windows' own items (common/actions:
 *  edit, delete, pin, mute, report, translate, lists…), the author's profile on top. */
@Composable
private fun CardMenu(p: PostItem, act: CardActions) {
    var open by remember { mutableStateOf(false) }
    var info by remember { mutableStateOf<JSONObject?>(null) }
    val clipboard = LocalClipboardManager.current
    LaunchedEffect(open) { if (open) info = (act.menu ?: act.info)(p) }
    Box {
        IconButton(onClick = { open = true }) {
            Icon(Icons.Filled.MoreVert, stringResource(R.string.more),
                tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            // the author first: on a phone the long menu's end is a scroll away
            if (p.accountId.isNotBlank()) {
                DropdownMenuItem(text = { Text(stringResource(R.string.profile_of, p.handle)) },
                    onClick = { open = false; act.profile(p.accountId) })
            }
            DropdownMenuItem(text = { Text(stringResource(if (p.shared) R.string.unboost else R.string.boost)) },
                onClick = { open = false; act.share(p) })
            val items = info?.optJSONArray("items")
            if (items == null) {  // the windows' menu has its own (and says when it's done)
                DropdownMenuItem(text = { Text(stringResource(if (p.bookmarked) R.string.unbookmark
                                                              else R.string.bookmark)) },
                    onClick = { open = false; act.bookmark(p) })
            }
            if (items != null) {
                for (i in 0 until items.length()) {
                    val item = items.getJSONObject(i)
                    val label = item.optString("label")
                    when (item.optString("kind")) {
                        "separator" -> HorizontalDivider()
                        "link" -> DropdownMenuItem(text = { Text(label) },
                            onClick = { open = false; act.runLink(item.optString("url")) })
                        "open" -> DropdownMenuItem(text = { Text(label) },
                            onClick = { open = false; act.browser(item.optString("url")) })
                        "copy" -> DropdownMenuItem(text = { Text(label) },
                            onClick = { open = false; clipboard.setText(AnnotatedString(item.optString("text"))) })
                        "quote_reply" -> DropdownMenuItem(text = { Text("❝ $label") },
                            onClick = { open = false; act.quoteReply(p) })
                        else -> item.optJSONObject("page")?.let { pg ->
                            DropdownMenuItem(text = { Text("$label …") }, onClick = {
                                open = false; act.page(pg.optString("page"), pg.optString("arg"))
                            })
                        }
                    }
                }
            } else {
                // the old short menu, while the windows' one is on its way (or failed)
                info?.let { i ->
                    val subbed = i.optBoolean("subscribed")
                    DropdownMenuItem(text = { Text(stringResource(if (subbed) R.string.unsub_thread
                                                                  else R.string.sub_thread)) },
                        onClick = { open = false; act.thread(p, if (subbed) "unsub" else "sub") })
                }
                if (p.url.isNotBlank()) {
                    DropdownMenuItem(text = { Text(stringResource(R.string.copy_link)) },
                        onClick = { open = false; clipboard.setText(AnnotatedString(p.url)) })
                    DropdownMenuItem(text = { Text(stringResource(R.string.open_browser)) },
                        onClick = { open = false; act.browser(p.url) })
                }
            }
        }
    }
}
