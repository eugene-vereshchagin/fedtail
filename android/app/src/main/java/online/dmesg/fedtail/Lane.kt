package online.dmesg.fedtail

import androidx.compose.foundation.background
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
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

/**
 * A lane (mockups "2" and "3"): the title opens the switcher; under it, the lanes with news
 * as chips; at the end of the lane, "read — next: …"; a swipe to the left goes there.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LaneScreen(
    model: AppModel, snack: SnackbarHostState, openBrowser: (String) -> Unit, state: LazyListState,
) {
    var switcher by remember { mutableStateOf(false) }
    val name = model.current ?: return
    val act = CardActions(
        open = { model.openThread(it.sid) }, reply = { model.compose(it) },
        like = { model.like(it) }, media = { list, i -> model.openMedia(list, i) },
        link = openBrowser, alias = { model.putAlias(it) })
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            Surface(color = MaterialTheme.colorScheme.surface) {
                Column {
                    TopAppBar(
                        colors = TopAppBarDefaults.topAppBarColors(
                            containerColor = MaterialTheme.colorScheme.surface),
                        navigationIcon = {
                            IconButton(onClick = { model.toOverview() }) {
                                Icon(Glyphs.Grid, stringResource(R.string.hub_title))
                            }
                        },
                        title = {
                            Row(Modifier.clickable { switcher = true }.padding(vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                Text(model.title, maxLines = 1, overflow = TextOverflow.Ellipsis,
                                    fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f, fill = false))
                                Icon(Icons.Filled.KeyboardArrowDown, stringResource(R.string.switch_lane),
                                    Modifier.size(20.dp))
                            }
                        },
                        actions = {
                            IconButton(onClick = { model.refresh() }) {
                                Icon(Icons.Filled.Refresh, stringResource(R.string.refresh))
                            }
                        })
                    NewsStrip(model, name)
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
                    Icon(Icons.Filled.Edit, stringResource(R.string.write))
                }
            }
        },
        snackbarHost = { SnackbarHost(snack) },
    ) { pad ->
        val density = LocalDensity.current
        var dragged by remember { mutableFloatStateOf(0f) }
        PullToRefreshBox(isRefreshing = model.pulling, onRefresh = { model.refresh(pulled = true) },
            modifier = Modifier.padding(pad).fillMaxSize()
                .pointerInput(name) {
                    val far = with(density) { 120.dp.toPx() }
                    detectHorizontalDragGestures(
                        onDragStart = { dragged = 0f },
                        onDragEnd = {
                            if (dragged < -far) model.nextLane()?.let { model.showLane(it.name) }
                            dragged = 0f
                        },
                        onHorizontalDrag = { _, dx -> dragged += dx })
                }) {
            LaunchedEffect(model.opening) {
                if (model.opening != model.aimed) { // opened anew — not just come back to
                    aim(state, model.posts, model.newestFirst)
                    model.aimed = model.opening
                }
            }
            MarkWhileScrolling(state, model.markOnScroll) { model.markRead(it) }
            PostList(model.posts, state, model.divider, act, model.hideSensitive,
                footer = { LaneEnd(model, name) })
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
            StripChip(l.title, "${l.unread}", on = false) { model.showLane(l.name) }
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

/** The end of a lane: read — what's next (the next lane with news, yours first). */
@Composable
private fun LaneEnd(model: AppModel, name: String) {
    val next = model.nextLane(after = name)
    Column(Modifier.fillMaxWidth().padding(top = 8.dp).clip(RoundedCornerShape(16.dp))
        .background(MaterialTheme.colorScheme.surface)
        .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(16.dp))
        .padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Glyphs.Done, null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.tertiary)
            Spacer(Modifier.width(8.dp))
            Text(stringResource(R.string.lane_done, model.title), fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.tertiary)
        }
        if (next != null) {
            Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clip(RoundedCornerShape(14.dp))
                .background(MaterialTheme.colorScheme.primary)
                .clickable { model.showLane(next.name) }.padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.next_lane), fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onPrimary)
                    Text("${next.title} · ${next.unread}", fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onPrimary)
                }
                Icon(Icons.AutoMirrored.Filled.ArrowForward, null,
                    tint = MaterialTheme.colorScheme.onPrimary)
            }
            Text(stringResource(R.string.swipe_hint), fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Text(stringResource(R.string.nothing_next), fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        TextButton(onClick = { model.toOverview() }) { Text(stringResource(R.string.to_overview)) }
    }
}

/** The switcher (mockup "3"): a search, the counted lanes as tiles, the browsed ones below. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Switcher(model: AppModel, close: () -> Unit) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var find by remember { mutableStateOf("") }
    val want = { title: String -> find.isBlank() || title.contains(find.trim(), ignoreCase = true) }
    val counted = model.hub.filter { it.kind != "browse" }
        .flatMap { s -> s.lanes.map { it to (s.kind == "you") } }.filter { want(it.first.title) }
    val browsed = model.hub.filter { it.kind == "browse" }.flatMap { it.lanes }.filter { want(it.title) }
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
            LazyVerticalGrid(GridCells.Fixed(4), Modifier.heightIn(max = 420.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(counted, key = { it.first.name }) { (lane, mine) ->
                    val on = lane.name == model.current
                    Column(Modifier.height(68.dp).clip(RoundedCornerShape(14.dp))
                        .background(when {
                            on -> MaterialTheme.colorScheme.onSurface
                            mine && lane.unread > 0 -> MaterialTheme.colorScheme.secondaryContainer
                            else -> MaterialTheme.colorScheme.surfaceVariant
                        })
                        .clickable { go(lane.name) }.padding(4.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center) {
                        val fg = if (on) MaterialTheme.colorScheme.surface else MaterialTheme.colorScheme.onSurface
                        Text(if (lane.unread > 0) "${lane.unread}" else "·", fontSize = 19.sp,
                            fontWeight = FontWeight.Bold, color = fg)
                        Text(lane.title, fontSize = 11.5.sp, color = fg, maxLines = 2,
                            lineHeight = 13.sp, textAlign = TextAlign.Center,
                            overflow = TextOverflow.Ellipsis)
                    }
                }
            }
            if (browsed.isNotEmpty()) {
                Text(stringResource(R.string.sec_browse).uppercase(), fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold, letterSpacing = 0.6.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                browsed.forEach { lane ->
                    Row(Modifier.fillMaxWidth().heightIn(min = 46.dp).clickable { go(lane.name) },
                        verticalAlignment = Alignment.CenterVertically) {
                        Text(lane.title, fontSize = 15.sp, modifier = Modifier.weight(1f))
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
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
