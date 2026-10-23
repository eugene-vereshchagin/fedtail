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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * The overview of lanes — the app's home (mockup "1"): every lane by kind, its count and
 * its first unread post, like a list of chats; "read in a row" walks the lanes with news,
 * what is addressed to you first. Lanes without counts (Federated, tags…) are only browsed.
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun HubScreen(model: AppModel, snack: SnackbarHostState, pane: Boolean = false) {
    var menu by remember { mutableStateOf(false) }
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            Column {
                TopAppBar(
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface),
                    title = {
                        Column {
                            Text(stringResource(R.string.hub_title), fontWeight = FontWeight.Bold)
                            Text((if (model.handle.isBlank()) "fedtail" else "@" + model.handle) +
                                    if (model.demo) " · demo" else "",
                                fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    },
                    actions = {
                        IconButton(onClick = { model.refresh() }) {
                            Icon(Icons.Filled.Refresh, stringResource(R.string.refresh))
                        }
                        Box {
                            IconButton(onClick = { menu = true }) {
                                Icon(Icons.Filled.MoreVert, stringResource(R.string.more))
                            }
                            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                                DropdownMenuItem(text = { Text(stringResource(R.string.sync)) },
                                    onClick = { menu = false; model.openSync() })
                                DropdownMenuItem(text = { Text(stringResource(R.string.config)) },
                                    onClick = { menu = false; model.openConfig() })
                            }
                        }
                    })
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
                item(key = "row") { ReadInRow(model) }
                val tiles = model.overview == "tiles"
                model.hub.filter { it.kind != "browse" }.forEach { sec ->
                    val mine = sec.kind == "you"
                    item(key = "h-" + sec.kind) { SectionHead(sec) }
                    if (tiles) {
                        // yours: big tiles with the first unread; the rest: small ones
                        val per = when {
                            mine -> 2
                            pane -> 2
                            else -> 3
                        }
                        val rows = sec.lanes.chunked(per)
                        items(rows.size, key = { "t-" + sec.kind + it }) { r ->
                            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                rows[r].forEach { lane ->
                                    LaneTile(lane, mine, big = mine,
                                        on = lane.name == model.current,
                                        modifier = Modifier.weight(1f)) { model.showLane(lane.name) }
                                }
                                repeat(per - rows[r].size) { Box(Modifier.weight(1f)) }
                            }
                        }
                    } else {
                        items(sec.lanes, key = { "l-" + it.name }) { lane ->
                            HubRow(lane, mine, on = lane.name == model.current) {
                                model.showLane(lane.name)
                            }
                        }
                    }
                }
                model.hub.firstOrNull { it.kind == "browse" }?.let { sec ->
                    item(key = "h-browse") { SectionHead(sec) }
                    item(key = "browse") {
                        FlowRow(Modifier.padding(horizontal = 16.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            sec.lanes.forEach { lane ->
                                Chip(lane.title) { model.showLane(lane.name) }
                            }
                        }
                    }
                }
            }
        }
    }
}

/** A lane as a tile (phone.overview = "tiles"): big — yours, with the first unread post. */
@Composable
private fun LaneTile(
    lane: HubLane, mine: Boolean, big: Boolean, on: Boolean, modifier: Modifier,
    onClick: () -> Unit,
) {
    val news = lane.unread > 0
    val bg = when {
        on -> MaterialTheme.colorScheme.onSurface
        mine && news -> MaterialTheme.colorScheme.secondaryContainer
        else -> MaterialTheme.colorScheme.surface
    }
    val fg = if (on) MaterialTheme.colorScheme.surface else MaterialTheme.colorScheme.onSurface
    val accent = when {
        on -> MaterialTheme.colorScheme.surface
        mine -> MaterialTheme.colorScheme.secondary
        else -> MaterialTheme.colorScheme.primary
    }
    Column(modifier.heightIn(min = if (big) 92.dp else 72.dp).clip(RoundedCornerShape(14.dp))
        .background(bg).clickable(onClick = onClick)
        .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterVertically),
        horizontalAlignment = if (big) Alignment.Start else Alignment.CenterHorizontally) {
        if (big) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(lane.title, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = fg,
                    maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                if (news) Text("${lane.unread}", fontSize = 22.sp, fontWeight = FontWeight.Bold,
                    color = accent)
            }
            if (lane.peek.isNotBlank()) {
                Text(lane.peek, fontSize = 12.sp, lineHeight = 15.sp, maxLines = 2,
                    overflow = TextOverflow.Ellipsis, color = fg.copy(alpha = 0.75f))
            }
        } else {
            Text(if (news) "${lane.unread}" else "", fontSize = 20.sp, fontWeight = FontWeight.Bold,
                color = accent)
            Text(lane.title, fontSize = 12.5.sp, color = fg, maxLines = 1,
                overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun ReadInRow(model: AppModel) {
    Surface(color = MaterialTheme.colorScheme.surface) {
        Box(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 14.dp)) {
            val any = model.hubUnread > 0
            Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clip(RoundedCornerShape(14.dp))
                .background(if (any) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.surfaceVariant)
                .clickable(enabled = any) { model.readInRow() }
                .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically) {
                val fg = if (any) MaterialTheme.colorScheme.onPrimary
                         else MaterialTheme.colorScheme.onSurfaceVariant
                Column(Modifier.weight(1f)) {
                    Text(stringResource(if (any) R.string.read_in_row else R.string.all_read),
                        color = fg, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    if (any) {
                        Text(stringResource(R.string.read_in_row_sub, model.hubUnread, model.hubWithNews),
                            color = fg, fontSize = 12.sp)
                    }
                }
                if (any) Icon(Icons.AutoMirrored.Filled.ArrowForward, null, tint = fg)
            }
        }
    }
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
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
                if (lane.unread > 0) Count(lane.unread, mine)
            }
            HorizontalDivider(Modifier.padding(start = 16.dp),
                color = MaterialTheme.colorScheme.surfaceVariant)
        }
    }
}

@Composable
fun Count(n: Int, mine: Boolean) {
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
