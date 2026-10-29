package online.dmesg.fedtail

import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * A lane (mockups "2" and "3"): the title opens the switcher; under it, the lanes with news
 * as chips; at the end of the lane, "read — next: …"; a swipe to the left goes there.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LaneScreen(
    model: AppModel, snack: SnackbarHostState, openBrowser: (String) -> Unit, state: LazyListState,
    pane: Boolean = false, // beside the overview (a tablet): no way back to it, no strip
) {
    var switcher by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val name = model.current ?: return
    val act = model.cardActions(openBrowser)
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            Surface(color = MaterialTheme.colorScheme.surface) {
                Column {
                    TopAppBar(
                        colors = TopAppBarDefaults.topAppBarColors(
                            containerColor = MaterialTheme.colorScheme.surface),
                        navigationIcon = {
                            if (!pane) IconButton(onClick = { model.toOverview() }) {
                                Icon(Glyphs.Grid, stringResource(R.string.hub_title))
                            }
                        },
                        title = {
                            Column(Modifier.clickable { switcher = true }.padding(vertical = 4.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(model.title, maxLines = 1, overflow = TextOverflow.Ellipsis,
                                        fontWeight = FontWeight.SemiBold,
                                        modifier = Modifier.weight(1f, fill = false))
                                    Icon(Icons.Filled.KeyboardArrowDown,
                                        stringResource(R.string.switch_lane), Modifier.size(20.dp))
                                }
                                // how fresh: "⟳ updating the lanes…" / "updated at 14:32" — an
                                // empty lane reads as nothing new, not as a dead network
                                if (model.hubSlow.isNotBlank()) {
                                    Text(model.hubSlow, fontSize = 12.sp, maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        },
                        actions = {
                            // "to the new" with how many there are, and "mark all read" — the
                            // windows' lane buttons (a bare arrow told nothing)
                            val unread = model.posts.count { it.unread }
                            if (unread > 0) {
                                val toNew = stringResource(R.string.to_new)
                                TextButton(onClick = {
                                    scope.launch {
                                        aim(state, model.posts, model.newestFirst,
                                            before = if (model.newestFirst) 0 else 1,
                                            divider = model.divider?.first)
                                    }
                                }, modifier = Modifier.semantics { contentDescription = toNew }) {
                                    Text((if (model.newestFirst) "↑ " else "↓ ") + unread, fontSize = 15.sp)
                                }
                                val allRead = stringResource(R.string.mark_all_read)
                                IconButton(onClick = { model.markLaneRead() },
                                    modifier = Modifier.semantics { contentDescription = allRead }) {
                                    Icon(Glyphs.Done, allRead)
                                }
                            }
                            IconButton(onClick = { model.findOpen = !model.findOpen }) {
                                Icon(Icons.Filled.Search, stringResource(R.string.find))
                            }
                            // the lane's rule: the windows' "Edit the lane…" (common/lanesplace.py);
                            // a list's or a tag group's lane stands in the editor's list of lanes
                            val editLane = stringResource(R.string.edit_lane)
                            IconButton(onClick = { model.editLane(name) },
                                modifier = Modifier.semantics { contentDescription = editLane }) {
                                Text("⚙", fontSize = 20.sp)
                            }
                            IconButton(onClick = { model.refresh() }) {
                                ThemedIcon("refresh", Icons.Filled.Refresh, stringResource(R.string.refresh))
                            }
                        })
                    if (!pane) AnnounceBar(model)
                    if (!pane) NewsStrip(model, name)
                    if (model.findOpen) FindBar(model)
                    model.laneSwitches?.let { Switches(model, it) }
                    // what the lane holds now ("a filter on: 12 of 40"); when empty, the
                    // empty lane says it itself
                    model.laneSwitches?.info?.takeIf { it.isNotBlank() && model.posts.isNotEmpty() }?.let {
                        Text(it, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp))
                    }
                    if (model.refreshing) LinearProgressIndicator(Modifier.fillMaxWidth())
                    else HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                }
            }
        },
        bottomBar = { if (model.commandLine) CommandBar(model) },
        floatingActionButton = {
            if (!model.commandLine) {
                FloatingActionButton(onClick = { model.compose(null) },
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary) {
                    ThemedIcon("write", Icons.Filled.Edit, stringResource(R.string.write))
                }
            }
        },
        snackbarHost = { SnackbarHost(snack) },
    ) { pad ->
        val density = LocalDensity.current
        var dragged by remember { mutableFloatStateOf(0f) }
        // the pull where the newest posts are: at the top, newest first; at the bottom,
        // read "as a forum" (oldest first) — there one drags up past the end
        val swipe = Modifier.padding(pad).fillMaxSize()
                .pointerInput(name) {
                    val far = with(density) { 120.dp.toPx() }
                    detectHorizontalDragGestures(
                        onDragStart = { dragged = 0f },
                        onDragEnd = {
                            if (dragged < -far) model.nextLane()?.let { model.showLane(it.name) }
                            dragged = 0f
                        },
                        onHorizontalDrag = { _, dx -> dragged += dx })
                }
        val body: @Composable () -> Unit = {
            // a match found (in the lane, or picked from every lane): the list stands on it
            LaunchedEffect(model.aimKey, model.posts) {
                val key = model.aimKey ?: return@LaunchedEffect
                val i = model.posts.indexOfFirst { it.key == key }
                if (i < 0) return@LaunchedEffect
                val line = model.divider?.first?.let { d -> model.posts.indexOfFirst { it.key == d } } ?: -1
                state.scrollToItem((if (model.newestFirst) 0 else 1) + i + if (line in 0 until i) 1 else 0)
                model.aimKey = null
                model.aimed = model.opening
            }
            LaunchedEffect(model.opening) {
                if (model.aimKey == null && model.opening != model.aimed) { // opened anew — not just come back to
                    aim(state, model.posts, model.newestFirst, before = if (model.newestFirst) 0 else 1,
                        divider = model.divider?.first, byCore = true, start = model.startKey)
                    model.aimed = model.opening
                }
            }
            MarkWhileScrolling(state, model.markOnScroll) { model.markRead(it) }
            StoodWhileScrolling(state, shown = { model.onScreen(it) }) { key, end ->
                if (model.aimKey == null) model.stood(key, end)
            }
            // "earlier" where the older posts would come: on top, or at the end when newest first
            val earlier: @Composable () -> Unit = {
                if (model.laneOlder) Earlier(model.loadingOlder,
                    seen = { model.loadOlder(ahead = true) }) { model.loadOlder() }
            }
            PostList(model.posts, state, model.divider, act, model.hideSensitive,
                prefetch = model.prefetch,
                emptyText = model.laneSwitches?.info?.takeIf { it.isNotBlank() },
                busy = model.busy,
                header = if (model.newestFirst) null else earlier,
                footer = {
                    Column {
                        if (model.newestFirst) earlier()
                        LaneEnd(model, name)
                    }
                })
        }
        if (model.newestFirst) {
            PullToRefreshBox(isRefreshing = model.pulling, onRefresh = { model.refresh(pulled = true) },
                modifier = swipe) { body() }
        } else {
            BottomPullToRefresh(refreshing = model.pulling, onRefresh = { model.refresh(pulled = true) },
                modifier = swipe) { body() }
        }
    }
    if (switcher) Switcher(model) { switcher = false }
    model.cmdConfirm?.let { ask ->
        AlertDialog(onDismissRequest = { model.cmdConfirm = null },
            text = { Text(ask) },
            confirmButton = { TextButton(onClick = { model.runCommand(confirmed = true) }) {
                Text(stringResource(R.string.yes_do)) } },
            dismissButton = { TextButton(onClick = { model.cmdConfirm = null }) {
                Text(stringResource(R.string.cancel)) } })
    }
}

/** "Earlier": the older posts of this lane, from the server. */
@Composable
private fun Earlier(busy: Boolean, seen: () -> Unit = {}, onClick: () -> Unit) {
    // composed — the list is near it: reading.older_ahead may fetch by itself (the core says)
    LaunchedEffect(Unit) { seen() }
    Box(Modifier.fillMaxWidth().padding(vertical = 4.dp), contentAlignment = Alignment.Center) {
        if (busy) CircularProgressIndicator(Modifier.size(28.dp))
        else TextButton(onClick = onClick) { Text(stringResource(R.string.earlier)) }
    }
}

/** The lanes with news, this one first: a tap is a lane. */
@Composable
private fun NewsStrip(model: AppModel, name: String) {
    val others = model.hub.filter { it.kind != "browse" }.flatMap { it.lanes }
        .filter { it.unread > 0 && it.name != name }
    if (others.isEmpty()) return
    LazyRow(contentPadding = PaddingValues(start = 12.dp, end = 12.dp, bottom = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        item(key = name) { StripChip(model.title, "", on = true) {} }
        items(others, key = { it.name }) { l ->
            StripChip(l.title, l.count, on = false) { model.showLane(l.name) }
        }
    }
}

@Composable
private fun StripChip(title: String, count: String, on: Boolean, onClick: () -> Unit) {
    Row(Modifier.height(32.dp).clip(RoundedCornerShape(16.dp))
        .background(if (on) MaterialTheme.colorScheme.onSurface
                    else MaterialTheme.colorScheme.surfaceVariant)
        .clickable(onClick = onClick).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically) {
        val fg = if (on) MaterialTheme.colorScheme.surface else MaterialTheme.colorScheme.onSurface
        Text(title, fontSize = 13.sp, color = fg, maxLines = 1,
            fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal)
        if (count.isNotBlank()) Text("  $count", fontSize = 13.sp, color = fg.copy(alpha = 0.8f))
    }
}

/** The end of a lane, one row: ✓ read — and the next lane with news (yours first) as a
 *  button; none — nothing. (It was a card half the screen high: a done mark, a big
 *  button, a hint, a link — the grid at the top goes to the lanes anyway, a swipe too.) */
@Composable
private fun LaneEnd(model: AppModel, name: String) {
    val next = model.nextLane(after = name)
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp).heightIn(min = 48.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(Glyphs.Done, null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.tertiary)
        Spacer(Modifier.width(8.dp))
        Text(stringResource(R.string.lane_done, model.title), fontSize = 14.sp,
            maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
            color = MaterialTheme.colorScheme.tertiary)
        if (next != null) {
            Button(onClick = { model.showLane(next.name) },
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)) {
                Text("${next.title} · ${next.count}", maxLines = 1,
                    overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.width(6.dp))
                Icon(Icons.AutoMirrored.Filled.ArrowForward, stringResource(R.string.next_lane),
                    Modifier.size(18.dp))
            }
        }
    }
}

/** The switcher (mockup "3"): a search, the counted lanes as tiles, the browsed ones below. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Switcher(model: AppModel, close: () -> Unit) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var find by remember { mutableStateOf("") }
    val want = { title: String -> find.isBlank() || title.contains(find.trim(), ignoreCase = true) }
    val counted = model.tileLanes().filter { want(it.first.title) }
    val browsed = model.restLanes().filter { want(it.first.title) }
    val go = { name: String -> close(); model.showLane(name) }
    ModalBottomSheet(onDismissRequest = close, sheetState = sheet,
        containerColor = MaterialTheme.colorScheme.surface) {
        Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 16.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth().height(44.dp).clip(RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant).padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Search, null, Modifier.size(18.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.width(8.dp))
                Box(Modifier.weight(1f)) {
                    if (find.isEmpty()) {
                        Text(stringResource(R.string.find_lane), fontSize = 15.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    BasicTextField(find, { find = it }, singleLine = true,
                        textStyle = TextStyle(fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface),
                        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                        modifier = Modifier.fillMaxWidth())
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                SmallHead(stringResource(if (model.hubPinned.isEmpty()) R.string.hub_title
                                         else R.string.sec_pinned), Modifier.weight(1f))
                TextButton(onClick = { close(); model.editPins() }) {
                    Text(stringResource(R.string.change))
                }
            }
            LazyVerticalGrid(GridCells.Fixed(4), Modifier.heightIn(max = 420.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(counted, key = { it.first.name }) { (lane, mine) ->
                    LaneTile(lane, mine, on = lane.name == model.current,
                        modifier = Modifier.fillMaxWidth()) { go(lane.name) }
                }
            }
            if (browsed.isNotEmpty()) {
                SmallHead(stringResource(R.string.sec_rest))
                Column {
                    browsed.forEach { (lane, only) -> RestRow(lane, only, inset = 0.dp) { go(lane.name) } }
                }
            }
        }
    }
}

/** Point's command line (ui.command_line): "#abc text" answers, "#abc" opens, and the rest
 *  of core/commands.py; what Enter will do is said above it while typing. */
@Composable
private fun CommandBar(model: AppModel) {
    LaunchedEffect(model.cmdText) {
        delay(250)
        model.cmdPreview(model.cmdText)
    }
    Surface(color = MaterialTheme.colorScheme.surface, modifier = Modifier.imePadding()) {
        Column(Modifier.navigationBarsPadding().padding(start = 12.dp, end = 8.dp, top = 6.dp, bottom = 8.dp)) {
            if (model.cmdHint.isNotBlank()) {
                Text(model.cmdHint, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(bottom = 4.dp))
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(">", fontFamily = FontFamily.Monospace, fontSize = 18.sp,
                    color = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(8.dp))
                Box(Modifier.weight(1f).heightIn(min = 44.dp).clip(RoundedCornerShape(8.dp))
                    .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(8.dp))
                    .padding(horizontal = 10.dp, vertical = 10.dp),
                    contentAlignment = Alignment.CenterStart) {
                    if (model.cmdText.isEmpty()) {
                        Text(stringResource(R.string.cmd_hint), fontFamily = FontFamily.Monospace,
                            fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    BasicTextField(model.cmdText, { model.cmdChanged(it) },
                        textStyle = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 14.sp,
                            color = MaterialTheme.colorScheme.onSurface),
                        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary), maxLines = 4,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { model.runCommand() }),
                        modifier = Modifier.fillMaxWidth())
                }
                IconButton(onClick = { model.runCommand() },
                    enabled = model.cmdText.isNotBlank() && !model.cmdBusy) {
                    Icon(Icons.AutoMirrored.Filled.Send, stringResource(R.string.send))
                }
            }
        }
    }
}

/** Finding in the lane (common/find.py's rule): ↑ ↓ through the matches, "deeper" —
 *  further back than it shows, "everywhere" — every lane. */
@Composable
private fun FindBar(model: AppModel) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            androidx.compose.material3.OutlinedTextField(value = model.findText,
                onValueChange = { model.findText = it }, singleLine = true,
                placeholder = { Text(stringResource(R.string.find)) },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { model.find() }),
                modifier = Modifier.weight(1f))
            TextButton(onClick = { model.find(-1) }, enabled = model.findIds.isNotEmpty()) { Text("↑") }
            TextButton(onClick = { model.find(1) }, enabled = model.findIds.isNotEmpty()) { Text("↓") }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (model.findWords.isNotBlank()) Text(model.findWords, fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
            else Spacer(Modifier.weight(1f))
            TextButton(onClick = { model.findDeeper() }, enabled = model.findText.isNotBlank()) {
                Text(stringResource(R.string.find_deeper))
            }
            TextButton(onClick = { model.findEverywhere() }, enabled = model.findText.isNotBlank()) {
                Text(stringResource(R.string.find_everywhere))
            }
        }
    }
}

/** The lane's switches (the windows' header): all / posts only / unread only, a whole
 *  conversation a card, which kinds of media. */
@Composable
private fun Switches(model: AppModel, sw: LaneSwitches) {
    if (sw.filters.isEmpty() && !sw.convOffered && sw.media.isEmpty() && sw.clear == null) return
    var mediaOpen by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())
        .padding(horizontal = 8.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        sw.filters.forEach { (key, words, _) ->
            androidx.compose.material3.FilterChip(selected = key == sw.filter,
                onClick = { model.laneSet(org.json.JSONObject().put("filter", key)) },
                label = { Text(words, fontSize = 13.sp) })
        }
        if (sw.convOffered && sw.convWords.size == 2) {
            androidx.compose.material3.FilterChip(selected = sw.convOn,
                onClick = { model.laneSet(org.json.JSONObject().put("conversations", !sw.convOn)) },
                label = { Text(sw.convWords[1], fontSize = 13.sp) })
        }
        if (sw.media.isNotEmpty()) {
            Box {
                androidx.compose.material3.FilterChip(selected = sw.mediaActive,
                    onClick = { mediaOpen = true }, label = { Text(sw.mediaLabel, fontSize = 13.sp) })
                androidx.compose.material3.DropdownMenu(expanded = mediaOpen,
                    onDismissRequest = { mediaOpen = false }) {
                    androidx.compose.material3.DropdownMenuItem(text = { Text(sw.mediaAll) }, onClick = {
                        mediaOpen = false
                        model.laneSet(org.json.JSONObject().put("media", "reset"))
                    })
                    sw.media.forEach { (kind, words, on) ->
                        androidx.compose.material3.DropdownMenuItem(
                            text = { Text((if (on) "☑ " else "☐ ") + words) },
                            onClick = {
                                model.laneSet(org.json.JSONObject().put("media", kind).put("on", !on))
                            })
                    }
                }
            }
        }
        // a lane of events only: every notification gone, on the server too (asked first)
        sw.clear?.let { (words, _) ->
            TextButton(onClick = { model.laneClear() }) { Text(words, fontSize = 13.sp) }
        }
    }
}
