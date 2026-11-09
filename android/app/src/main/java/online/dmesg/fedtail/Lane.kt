package online.dmesg.fedtail

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarResult
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.foundation.layout.widthIn
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
import androidx.compose.material3.SmallFloatingActionButton
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
 * A lane (the mockups "E", 09.11): one bar over it — ⊞ the home screen, the strip of lanes
 * (the open one its title; a tap on it — the switcher), filters, ⋮ — folding into a pill
 * while reading; at the end of the lane, "read — next: …"; a swipe to the left goes there.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LaneScreen(
    model: AppModel, snack: SnackbarHostState, openBrowser: (String) -> Unit, state: LazyListState,
    pane: Boolean = false, // beside the overview (a tablet): no ⊞ back to it; the strip stays
) {
    var switcher by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val name = model.current ?: return
    val act = model.cardActions(openBrowser)
    // the bar over the lane (09.11, the mockups "E"): one row — ⊞ the home screen, the
    // strip of lanes (the open one is the title), filters, ⋮ — laid over the list, not
    // above it: reading on it folds into a pill, a little scroll back brings it whole,
    // and the posts never move under the finger as it comes and goes
    var collapsed by remember(name) { mutableStateOf(false) }
    var filterSheet by remember { mutableStateOf(false) }
    val density = LocalDensity.current
    var headerPx by remember { mutableIntStateOf(0) }
    val collapse = remember(name) {
        object : NestedScrollConnection {
            var run = 0f
            override fun onPreScroll(available: Offset, source: NestedScrollSource): Offset {
                val dy = available.y  // < 0: the finger goes up — reading on
                run = if ((dy < 0) == (run < 0)) run + dy else dy
                if (run < -with(density) { 24.dp.toPx() }) collapsed = true
                else if (run > with(density) { 12.dp.toPx() }) collapsed = false
                return Offset.Zero
            }
        }
    }
    LaunchedEffect(state, name) {  // the list's very top: the bar whole
        snapshotFlow { state.firstVisibleItemIndex == 0 && state.firstVisibleItemScrollOffset == 0 }
            .collect { if (it) collapsed = false }
    }
    // "mark all read" goes to the core in 5 s: "Undo" meanwhile
    val allReadWords = stringResource(R.string.all_read)
    val undoWords = stringResource(R.string.undo)
    LaunchedEffect(model.readUndo) {
        if (model.readUndo == null) return@LaunchedEffect
        val got = snack.showSnackbar(allReadWords, actionLabel = undoWords,
            duration = SnackbarDuration.Short)
        if (got == SnackbarResult.ActionPerformed) model.undoLaneRead()
    }
    val unread = model.posts.count { it.unread }
    val firstUnread = model.posts.firstOrNull { it.unread }?.key
    // "↓ N" only where it leads somewhere: the first new post off the screen (or, none
    // new, the newest end away)
    val toNewWanted by remember(firstUnread, unread, model.newestFirst) {
        derivedStateOf {
            if (unread > 0) state.layoutInfo.visibleItemsInfo.none { it.key == firstUnread }
            else if (model.newestFirst) state.firstVisibleItemIndex > 0 else state.canScrollForward
        }
    }
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = { if (model.commandLine) CommandBar(model) },
        floatingActionButton = {
            Column(horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (model.toNewBottom && toNewWanted) ToNewButton(model, state, scope, unread,
                    floating = true)
                if (!model.commandLine) {
                    FloatingActionButton(onClick = { model.compose(null) },
                        containerColor = MaterialTheme.colorScheme.primary,
                        contentColor = MaterialTheme.colorScheme.onPrimary) {
                        ThemedIcon("write", Icons.Filled.Edit, stringResource(R.string.write))
                    }
                }
            }
        },
        snackbarHost = { SnackbarHost(snack) },
    ) { pad ->
        var dragged by remember { mutableFloatStateOf(0f) }
        // the pull where the newest posts are: at the top, newest first; at the bottom,
        // read "as a forum" (oldest first) — there one drags up past the end
        val swipe = Modifier.fillMaxSize()
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
        val topRoom = with(density) { headerPx.toDp() } + 8.dp
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
                    val at = aim(state, model.posts, model.newestFirst, before = if (model.newestFirst) 0 else 1,
                        divider = model.divider?.first, byCore = true, start = model.startKey,
                        bottom = model.startBottom)
                    model.aimed = model.opening
                    model.holding = true  // where it stood: said once the place stands
                    try { holdPlace(state, at, model.startBottom) } finally { model.holding = false }
                }
            }
            MarkWhileScrolling(state, model.markOnScroll, model.dwellMs) { model.markRead(it) }
            StoodWhileScrolling(state, shown = { model.onScreen(it) }) { key, end ->
                if (model.aimKey == null && !model.holding) model.stood(key, end)
            }
            // "earlier" where the older posts would come: on top, or at the end when newest first
            val earlier: @Composable () -> Unit = {
                if (model.laneOlder) Earlier(model.loadingOlder,
                    seen = { model.loadOlder(ahead = true) }) { model.loadOlder() }
            }
            PostList(model.posts, state, model.divider, act, model.hideSensitive,
                prefetch = model.prefetch, topRoom = topRoom,
                emptyText = model.laneSwitches?.info?.takeIf { it.isNotBlank() },
                busy = model.busy,
                // the last post's end readable above the floating buttons: "write" and,
                // by the thumb, "↓ N" over it
                bottomRoom = if (model.toNewBottom) 160 else 96,
                header = if (model.newestFirst) null else earlier,
                footer = {
                    Column {
                        if (model.newestFirst) earlier()
                        LaneEnd(model, name)
                    }
                })
        }
        Box(Modifier.padding(pad).fillMaxSize().nestedScroll(collapse)) {
            if (model.newestFirst) {
                PullToRefreshBox(isRefreshing = model.pulling, onRefresh = { model.refresh(pulled = true) },
                    modifier = swipe) { body() }
            } else {
                BottomPullToRefresh(refreshing = model.pulling, onRefresh = { model.refresh(pulled = true) },
                    modifier = swipe) { body() }
            }
            AnimatedVisibility(!collapsed, Modifier.align(Alignment.TopCenter),
                enter = slideInVertically { -it } + fadeIn(),
                exit = slideOutVertically { -it } + fadeOut()) {
                Box(Modifier.onSizeChanged { headerPx = it.height }) {
                    LaneHeader(model, name, pane, state, scope, { switcher = true },
                        { filterSheet = true })
                }
            }
            AnimatedVisibility(collapsed, Modifier.align(Alignment.TopCenter).padding(top = 6.dp),
                enter = fadeIn(), exit = fadeOut()) {
                LanePill(model, name, { collapsed = false }, { switcher = true })
            }
        }
    }
    if (filterSheet) model.laneSwitches?.let { sw ->
        ModalBottomSheet(onDismissRequest = { filterSheet = false }) {
            Column(Modifier.padding(bottom = 24.dp)) {
                Text(stringResource(R.string.lane_filters), fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
                Switches(model, sw)
                sw.info.takeIf { it.isNotBlank() }?.let {
                    Text(it, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
                }
            }
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

/** Is a lane's filter on (a quick filter not the first, the funnel, talks only)? */
private fun filtering(sw: LaneSwitches): Boolean =
    sw.mediaActive || sw.convOn || (sw.filters.isNotEmpty() && sw.filter != sw.filters.first().first)

private fun hasFilters(sw: LaneSwitches): Boolean =
    sw.filters.isNotEmpty() || sw.convOffered || sw.media.isNotEmpty() || sw.clear != null

/** The bar over a lane: ⊞ (the home screen; not in a pane beside it), the strip of lanes,
 *  the filters (a dot when one is on), ⋮; under them a thin line — how fresh, what the
 *  filters hide, "offline". */
@Composable
private fun LaneHeader(model: AppModel, name: String, pane: Boolean, state: LazyListState,
                       scope: kotlinx.coroutines.CoroutineScope, onSwitcher: () -> Unit,
                       onFilter: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surface, shadowElevation = 2.dp) {
        Column(Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically) {
                if (!pane) IconButton(onClick = { model.toOverview() },
                    modifier = Modifier.size(48.dp)) {
                    Icon(Glyphs.Grid, stringResource(R.string.hub_title))
                }
                LaneStrip(model, name, Modifier.weight(1f), onSwitcher)
                val sw = model.laneSwitches
                if (sw != null && hasFilters(sw)) {
                    val on = filtering(sw)
                    val words = stringResource(if (on) R.string.lane_filters_on else R.string.lane_filters)
                    Box(Modifier.size(48.dp).clip(CircleShape)
                        .background(if (on) MaterialTheme.colorScheme.tertiaryContainer
                                    else Color.Transparent)
                        .clickable(onClick = onFilter)
                        .semantics { contentDescription = words; role = Role.Button },
                        contentAlignment = Alignment.Center) {
                        Icon(Glyphs.Filter, null, Modifier.size(22.dp),
                            tint = if (on) MaterialTheme.colorScheme.onTertiaryContainer
                                   else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                LaneMore(model, name, state, scope, onSwitcher)
            }
            val unseen = stringResource(R.string.offline)
            // more accounts, each its own lanes: whose these are
            val whose = if (model.accountCount > 1 && !model.merged && model.handle.isNotBlank())
                "@" + model.handle else ""
            val line = listOf(if (model.offline) unseen else "", whose, model.hubSlow,
                model.laneSwitches?.info?.takeIf { model.posts.isNotEmpty() } ?: "")
                .filter { it.isNotBlank() }.joinToString(" · ")
            if (line.isNotBlank()) {
                Text(line, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    color = if (model.offline) MaterialTheme.colorScheme.error
                            else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 4.dp))
            }
            if (!pane) AnnounceBar(model)
            if (model.findOpen) FindBar(model)
            if (model.refreshing) LinearProgressIndicator(Modifier.fillMaxWidth())
            else HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        }
    }
}

/** The strip (common/sidebar.strip): the main lanes — a picture and the count
 *  (phone.lane_strip = "icons") — a line, the others with news by name; the open one
 *  with its picture, name and count, kept in sight: it is the title. Its tap — the
 *  switcher (every lane). */
@Composable
private fun LaneStrip(model: AppModel, name: String, modifier: Modifier, onSwitcher: () -> Unit) {
    val byName = remember(model.hub) { model.hub.flatMap { it.lanes }.associateBy { it.name } }
    val items = remember(model.strip, name) {
        val s = model.strip
        if (s.any { it.name == name }) s
        else {  // a lane out of the strip (a browsed one): itself, after the main ones
            val main = s.takeWhile { it.main }
            main + StripLane(name, "", false) + s.drop(main.size)
        }
    }
    val listState = rememberLazyListState()
    LaunchedEffect(name, items.size) {
        val i = items.indexOfFirst { it.name == name }
        if (i >= 0) listState.animateScrollToItem(maxOf(0, i - 1))
    }
    LazyRow(state = listState, modifier = modifier,
        contentPadding = PaddingValues(horizontal = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        itemsIndexed(items, key = { _, it -> it.name }) { i, s ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (i > 0 && !s.main && items[i - 1].main) {
                    Box(Modifier.padding(end = 6.dp).width(1.dp).height(24.dp)
                        .background(MaterialTheme.colorScheme.outlineVariant))
                }
                val lane = byName[s.name]
                val on = s.name == name
                LaneChip(title = lane?.title ?: model.title,
                    count = lane?.takeIf { it.unread > 0 }?.count ?: "",
                    icon = s.icon, main = s.main,
                    iconOnly = model.stripIcons && s.main && !on && s.icon.isNotBlank(), on = on,
                    onClick = { if (on) onSwitcher() else model.showLane(s.name) })
            }
        }
    }
}

@Composable
private fun LaneChip(title: String, count: String, icon: String, main: Boolean,
                     iconOnly: Boolean, on: Boolean, onClick: () -> Unit) {
    val bg = when {
        on -> MaterialTheme.colorScheme.onSurface
        main -> MaterialTheme.colorScheme.surfaceVariant
        else -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f)
    }
    val fg = if (on) MaterialTheme.colorScheme.surface else MaterialTheme.colorScheme.onSurface
    val said = if (on) stringResource(R.string.lane_current, title) else title
    Row(Modifier.heightIn(min = 44.dp).clip(RoundedCornerShape(22.dp)).background(bg)
        .clickable(onClick = onClick)
        .semantics(mergeDescendants = true) {
            contentDescription = if (count.isBlank()) said else "$said, $count"
            role = Role.Tab; selected = on
        }
        .padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (icon.isNotBlank()) ThemedIcon("lane.$icon", Glyphs.Grid, null, Modifier.size(20.dp), tint = fg)
        if (!iconOnly || icon.isBlank()) {
            Text(title, fontSize = 14.sp, color = fg, maxLines = 1, overflow = TextOverflow.Ellipsis,
                fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal,
                modifier = Modifier.widthIn(max = 150.dp))
        }
        if (count.isNotBlank()) Text(count, fontSize = 14.sp, color = fg,
            fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal)
    }
}

/** ⋮ over a lane: find, mark all read (undone within 5 s), refresh, the lane's rule, the
 *  switcher — and "to the new" when it isn't floating by the thumb (phone.to_new). */
@Composable
private fun LaneMore(model: AppModel, name: String, state: LazyListState,
                     scope: kotlinx.coroutines.CoroutineScope, onSwitcher: () -> Unit) {
    var open by remember { mutableStateOf(false) }
    val words = stringResource(R.string.lane_more)
    Box {
        IconButton(onClick = { open = true }, modifier = Modifier.size(48.dp)
            .semantics { contentDescription = words }) {
            Icon(Icons.Filled.MoreVert, null)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            val unread = model.posts.count { it.unread }
            if (!model.toNewBottom) DropdownMenuItem(text = { Text(stringResource(R.string.to_new)) },
                onClick = { open = false; scope.launch {
                    aim(state, model.posts, model.newestFirst,
                        before = if (model.newestFirst) 0 else 1, divider = model.divider?.first) } })
            DropdownMenuItem(text = { Text(stringResource(R.string.find)) },
                onClick = { open = false; model.findOpen = !model.findOpen })
            if (unread > 0) DropdownMenuItem(text = { Text(stringResource(R.string.mark_all_read)) },
                onClick = { open = false; model.markLaneRead() })
            DropdownMenuItem(text = { Text(stringResource(R.string.refresh)) },
                onClick = { open = false; model.refresh() })
            DropdownMenuItem(text = { Text(stringResource(R.string.switch_lane)) },
                onClick = { open = false; onSwitcher() })
            DropdownMenuItem(text = { Text(stringResource(R.string.edit_lane)) },
                onClick = { open = false; model.editLane(name) })
        }
    }
}

/** The bar folded while reading: the lane's picture and name, a filter's mark, "offline";
 *  a tap — the bar whole; a long press — the switcher. The count stays on "↓ N". */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun LanePill(model: AppModel, name: String, onExpand: () -> Unit, onSwitcher: () -> Unit) {
    val icon = model.strip.firstOrNull { it.name == name }?.icon ?: ""
    val sw = model.laneSwitches
    val words = stringResource(R.string.show_header, model.title)
    Surface(shape = RoundedCornerShape(22.dp), color = MaterialTheme.colorScheme.surfaceVariant,
        shadowElevation = 3.dp,
        modifier = Modifier.heightIn(min = 48.dp)
            .combinedClickable(onClick = onExpand, onLongClick = onSwitcher)
            .semantics { contentDescription = words; role = Role.Button }) {
        Row(Modifier.padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (icon.isNotBlank()) ThemedIcon("lane.$icon", Glyphs.Grid, null, Modifier.size(18.dp))
            Text(model.title, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 200.dp))
            if (model.offline) Text(stringResource(R.string.offline), fontSize = 13.sp,
                color = MaterialTheme.colorScheme.error)
            if (sw != null && filtering(sw)) Icon(Glyphs.Filter, null, Modifier.size(16.dp),
                tint = MaterialTheme.colorScheme.tertiary)
        }
    }
}

/** "To the new" with how many there are — the windows' lane button (a bare arrow told
 *  nothing). Nothing new: the arrow stays and goes to the newest end, as the windows' does
 *  (after "mark all read" the end was a long scroll away, 02.11). floating: a small round
 *  button over "write" (phone.to_new = "bottom"), else a text button in the lane's bar. */
@Composable
private fun ToNewButton(model: AppModel, state: LazyListState,
                        scope: kotlinx.coroutines.CoroutineScope, unread: Int,
                        floating: Boolean = false) {
    val toNew = stringResource(if (unread > 0) R.string.to_new else R.string.to_end)
    val go: () -> Unit = {
        scope.launch {
            aim(state, model.posts, model.newestFirst,
                before = if (model.newestFirst) 0 else 1, divider = model.divider?.first)
        }
    }
    val words = (if (model.newestFirst) "↑" else "↓") + (if (unread > 0) " $unread" else "")
    if (floating) {
        SmallFloatingActionButton(onClick = go,
            containerColor = MaterialTheme.colorScheme.secondaryContainer,
            contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
            modifier = Modifier.semantics { contentDescription = toNew }) {
            Text(words, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(horizontal = 10.dp))
        }
    } else {
        TextButton(onClick = go, modifier = Modifier.semantics { contentDescription = toNew }) {
            Text(words, fontSize = 15.sp)
        }
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
