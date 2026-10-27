package online.dmesg.fedtail

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * The overview of lanes — the app's home (mockup "1"): every lane by kind, its count and
 * its first unread post, like a list of chats; the rest as the set has them (lanes.preset).
 * Lanes without counts (Federated, tags…) are only browsed.
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun HubScreen(model: AppModel, snack: SnackbarHostState, pane: Boolean = false) {
    var menu by remember { mutableStateOf(false) }
    val tiles = model.overview == "tiles"
    Scaffold(
        // tiles: grey tiles on white, as the switcher's sheet (mockup "3"); a list: white rows on grey
        containerColor = if (tiles) MaterialTheme.colorScheme.surface
                         else MaterialTheme.colorScheme.background,
        topBar = {
            Column {
                TopAppBar(
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface),
                    title = {
                        Column {
                            Text(stringResource(R.string.hub_title), fontWeight = FontWeight.Bold)
                            Text((if (model.handle.isBlank()) "fedtail" else "@" + model.handle) +
                                    (if (model.demo) " · demo" else "") +
                                    // how fresh, slow mode: "updated at 14:32 · next at 14:45"
                                    (if (model.hubSlow.isNotBlank()) " · " + model.hubSlow else ""),
                                fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    },
                    actions = {
                        IconButton(onClick = { model.refresh() }) {
                            ThemedIcon("refresh", Icons.Filled.Refresh, stringResource(R.string.refresh))
                        }
                        Box {
                            IconButton(onClick = { menu = true }) {
                                Icon(Icons.Filled.MoreVert, stringResource(R.string.more))
                            }
                            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                                // every place of the windows' ≡ menu: search, lists, the server…
                                DropdownMenuItem(text = { Text(stringResource(R.string.places)) },
                                    onClick = { menu = false; model.openPlacesMenu() })
                                // the windows' "accounts": add, switch, log in again, out
                                DropdownMenuItem(text = { Text(stringResource(R.string.accounts)) },
                                    onClick = { menu = false; model.openPage("accounts") })
                                if (model.accountCount > 1 || model.merged) {
                                    DropdownMenuItem(text = {
                                        Text((if (model.merged) "☑ " else "☐ ") +
                                            stringResource(R.string.merge_accounts))
                                    }, onClick = { menu = false; model.toggleMerge() })
                                }
                                DropdownMenuItem(text = { Text(stringResource(R.string.new_post)) },
                                    onClick = { menu = false; model.compose(null) })
                                DropdownMenuItem(text = { Text(stringResource(R.string.try_theme)) },
                                    onClick = { menu = false; model.tryTheme() })
                                DropdownMenuItem(text = { Text(stringResource(R.string.sync)) },
                                    onClick = { menu = false; model.openSync() })
                                DropdownMenuItem(text = { Text(stringResource(R.string.settings)) },
                                    onClick = { menu = false; model.openSettings() })
                                DropdownMenuItem(text = { Text(stringResource(R.string.config)) },
                                    onClick = { menu = false; model.openConfig() })
                                if (BuildConfig.DEBUG) {  // dev builds only
                                    DropdownMenuItem(text = { Text(stringResource(R.string.selfcheck)) },
                                        onClick = { menu = false; model.openSelfCheck() })
                                }
                            }
                        }
                    })
                AnnounceBar(model)
                if (model.refreshing) LinearProgressIndicator(Modifier.fillMaxWidth())
            }
        },
        floatingActionButton = {
            if (!pane) FloatingActionButton(onClick = { model.compose(null) },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary) {
                Icon(Icons.Filled.Edit, stringResource(R.string.write))
            }
        },
        snackbarHost = { SnackbarHost(snack) },
    ) { pad ->
        PullToRefreshBox(isRefreshing = model.pulling, onRefresh = { model.refresh(pulled = true) },
            modifier = Modifier.padding(pad).fillMaxSize()) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 96.dp)) {
                if (tiles) tileGrid(model, pane) else laneRows(model)
            }
        }
    }
}

/** The tiles (mockup "3"): phone.pinned in its order (or every counted lane) — yours tinted
 *  when there's news, the open one dark — four in a row; below, the rest as rows. */
private fun androidx.compose.foundation.lazy.LazyListScope.tileGrid(model: AppModel, pane: Boolean) {
    val tiles = model.tileLanes()
    val per = if (pane) 3 else 4
    val rows = tiles.chunked(per)
    item(key = "h-tiles") {
        Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp, top = 12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            SmallHead(stringResource(if (model.hubPinned.isEmpty()) R.string.hub_title
                                     else R.string.sec_pinned), Modifier.weight(1f))
            TextButton(onClick = { model.editTiles = !model.editTiles }) {
                Text(stringResource(if (model.editTiles) R.string.done else R.string.change))
            }
        }
    }
    if (model.editTiles) {
        pinEditor(model)
        return
    }
    items(rows.size, key = { "t-$it" }) { r ->
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            rows[r].forEach { (lane, mine) ->
                LaneTile(lane, mine, on = lane.name == model.current,
                    modifier = Modifier.weight(1f)) { model.showLane(lane.name) }
            }
            repeat(per - rows[r].size) { Box(Modifier.weight(1f)) }
        }
    }
    // the rest as the set has them (lanes.preset), under its sections' titles
    val rest = model.restLanes()
    if (rest.isEmpty()) return
    var last: String? = null
    rest.forEachIndexed { i, (lane, browsed) ->
        val head = lane.group
        if (head != last) {
            item(key = "h-rest-$i") {
                SmallHead(head.ifBlank { stringResource(R.string.sec_rest) },
                    Modifier.padding(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 4.dp))
            }
            last = head
        }
        item(key = "r-" + lane.name) {
            RestRow(lane, browsed) { model.showLane(lane.name) }
        }
    }
}

/** "Change" over the tiles: the tiles as rows to move (↑ ↓) or take away (✕), and the
 *  other lanes to add (＋). The core keeps the order; sync carries it to the other devices. */
private fun androidx.compose.foundation.lazy.LazyListScope.pinEditor(model: AppModel) {
    val tiles = model.tileLanes().map { it.first }
    items(tiles, key = { "p-" + it.name }) { lane ->
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(start = 16.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text(lane.title, fontSize = 16.sp, modifier = Modifier.weight(1f))
            TextButton(onClick = { model.moveTile(lane.name, -1) }) { Text("↑", fontSize = 18.sp) }
            TextButton(onClick = { model.moveTile(lane.name, +1) }) { Text("↓", fontSize = 18.sp) }
            TextButton(onClick = { model.pinTile(lane.name, false) }) { Text("✕", fontSize = 16.sp) }
        }
        HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.surfaceVariant)
    }
    val rest = model.restLanes().map { it.first }
    if (rest.isEmpty()) return
    item(key = "p-h-rest") {
        SmallHead(stringResource(R.string.sec_rest),
            Modifier.padding(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 4.dp))
    }
    items(rest, key = { "p-r-" + it.name }) { lane ->
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(start = 16.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text(lane.title, fontSize = 16.sp, modifier = Modifier.weight(1f),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(onClick = { model.pinTile(lane.name, true) }) { Text("＋", fontSize = 18.sp) }
        }
        HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.surfaceVariant)
    }
}

@Composable
fun SmallHead(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
        letterSpacing = 0.6.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier)
}

/** A lane under the tiles: its count on the right, or "browsed" for one without counts. */
@Composable
fun RestRow(lane: HubLane, browsed: Boolean, inset: Dp = 16.dp, onClick: () -> Unit) {
    Column(Modifier.padding(horizontal = inset)) {
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clickable(onClick = onClick),
            verticalAlignment = Alignment.CenterVertically) {
            Text(lane.title, fontSize = 16.sp, modifier = Modifier.weight(1f))
            Text(when {
                browsed -> stringResource(R.string.browsed)
                lane.unread > 0 -> lane.count
                else -> ""
            }, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
    }
}

/** The list (phone.overview = "list"): sections, a row per lane with its first unread post. */
@OptIn(ExperimentalLayoutApi::class)
private fun androidx.compose.foundation.lazy.LazyListScope.laneRows(model: AppModel) {
    model.hub.filter { it.kind != "browse" }.forEach { sec ->
        val mine = sec.kind == "you"
        item(key = "h-" + sec.kind) { SectionHead(sec) }
        items(sec.lanes, key = { "l-" + it.name }) { lane ->
            HubRow(lane, mine, on = lane.name == model.current) { model.showLane(lane.name) }
        }
    }
    model.hub.firstOrNull { it.kind == "browse" }?.let { sec ->
        item(key = "h-browse") { SectionHead(sec) }
        item(key = "browse") {
            FlowRow(Modifier.padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                sec.lanes.forEach { lane -> Chip(lane.title) { model.showLane(lane.name) } }
            }
        }
    }
}

/** A lane as a tile — the overview's (phone.overview = "tiles") and the switcher's. */
@Composable
fun LaneTile(
    lane: HubLane, mine: Boolean, on: Boolean, modifier: Modifier,
    plain: Color = MaterialTheme.colorScheme.surfaceVariant,
    onClick: () -> Unit,
) {
    val news = lane.unread > 0
    val bg = when {
        on -> MaterialTheme.colorScheme.onSurface
        mine && news -> MaterialTheme.colorScheme.secondaryContainer
        else -> plain
    }
    val fg = if (on) MaterialTheme.colorScheme.surface else MaterialTheme.colorScheme.onSurface
    Column(modifier.height(92.dp).clip(RoundedCornerShape(16.dp)).background(bg)
        .clickable(onClick = onClick).padding(4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterVertically)) {
        if (news) {
            Text(lane.count, fontSize = 24.sp, fontWeight = FontWeight.Bold, color = fg)
        }
        Text(lane.title, fontSize = 13.sp, lineHeight = 15.sp, color = fg,
            maxLines = if (news && lane.fresh > 0) 1 else 2,
            textAlign = TextAlign.Center, overflow = TextOverflow.Ellipsis)
        // "of them new 56": what the last update brought, smaller, under the title
        if (news && lane.fresh > 0) {
            Text(stringResource(R.string.fresh_of_them, lane.fresh), fontSize = 11.sp,
                lineHeight = 13.sp, color = fg.copy(alpha = 0.75f), maxLines = 1,
                textAlign = TextAlign.Center, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** The server's announcements (ui.announcements = "banner"): one at a time over the lanes,
 *  its reactions, and "Got it" — the server remembers it, other clients stop showing it. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AnnounceBar(model: AppModel) {
    val a = model.announces.firstOrNull() ?: return
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.secondaryContainer)
        .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(a.head, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
                modifier = Modifier.weight(1f))
            TextButton(onClick = { model.dismissAnnouncement() }) {
                Text(model.announceOk.ifBlank { "OK" })
            }
        }
        Text(a.text, fontSize = 14.sp, maxLines = 8, overflow = TextOverflow.Ellipsis,
            color = MaterialTheme.colorScheme.onSecondaryContainer)
        if (a.reactions.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                a.reactions.forEach { (name, count, mine) ->
                    androidx.compose.material3.FilterChip(selected = mine,
                        onClick = { model.reactAnnouncement(a, name) },
                        label = { Text(if (count > 0) "$name $count" else name, fontSize = 13.sp) })
                }
            }
        }
    }
}

@Composable
private fun SectionHead(sec: HubSection) {
    val words = when (sec.kind) {
        "you" -> R.string.sec_you
        "reading" -> R.string.sec_reading
        "lists" -> R.string.sec_lists
        else -> R.string.sec_browse
    }
    val sum = sec.lanes.sumOf { it.unread }
    Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 6.dp)) {
        Text(stringResource(words).uppercase(), fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
            letterSpacing = 0.6.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f))
        if (sum > 0) {
            Text("$sum", fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun HubRow(lane: HubLane, mine: Boolean, on: Boolean, onClick: () -> Unit) {
    Surface(color = if (on) MaterialTheme.colorScheme.primaryContainer
                    else MaterialTheme.colorScheme.surface, modifier = Modifier.fillMaxWidth()) {
        Column {
            Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(onClick = onClick)
                .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(lane.title, fontSize = 15.sp,
                        fontWeight = if (lane.unread > 0) FontWeight.SemiBold else FontWeight.Normal,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (lane.peek.isNotBlank()) {
                        Text(lane.peek, fontSize = 13.sp, maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                if (lane.unread > 0) Column(horizontalAlignment = Alignment.End) {
                    Count(lane.count, mine)
                    if (lane.fresh > 0) {
                        Text(stringResource(R.string.fresh_of_them, lane.fresh), fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            HorizontalDivider(Modifier.padding(start = 16.dp),
                color = MaterialTheme.colorScheme.surfaceVariant)
        }
    }
}

@Composable
fun Count(n: String, mine: Boolean) {
    Box(Modifier.heightIn(min = 24.dp).clip(RoundedCornerShape(12.dp))
        .background(if (mine) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.primary)
        .padding(horizontal = 8.dp, vertical = 2.dp), contentAlignment = Alignment.Center) {
        Text("$n", fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
            color = if (mine) MaterialTheme.colorScheme.onSecondary
                    else MaterialTheme.colorScheme.onPrimary)
    }
}

@Composable
fun Chip(text: String, onClick: () -> Unit) {
    Box(Modifier.height(36.dp).clip(RoundedCornerShape(18.dp))
        .background(MaterialTheme.colorScheme.surface)
        .clickable(onClick = onClick).padding(horizontal = 14.dp),
        contentAlignment = Alignment.Center) {
        Text(text, fontSize = 14.sp, maxLines = 1)
    }
}
