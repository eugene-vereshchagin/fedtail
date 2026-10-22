package online.dmesg.fedtail

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Badge
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun App(model: AppModel, openBrowser: (String) -> Unit) {
    val snack = remember { SnackbarHostState() }
    LaunchedEffect(model.message) {
        model.message?.let {
            snack.showSnackbar(it)
            model.message = null
        }
    }
    when (val s = model.screen) {
        Screen.Starting -> Centered { Starting() }
        is Screen.Failed -> Problem(s.text)
        Screen.Login -> Scaffold(snackbarHost = { SnackbarHost(snack) }) { pad ->
            Login(model, openBrowser, Modifier.padding(pad))
        }
        Screen.Main -> Main(model, snack)
    }
}

@Composable
private fun Centered(content: @Composable () -> Unit) {
    Surface(Modifier.fillMaxSize()) {
        Box(contentAlignment = Alignment.Center) { content() }
    }
}

@Composable
private fun Starting() {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator()
        Text(stringResource(R.string.starting))
    }
}

@Composable
private fun Problem(text: String) {
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Spacer(Modifier.height(32.dp))
            Text(stringResource(R.string.core_failed), style = MaterialTheme.typography.headlineSmall,
                color = MaterialTheme.colorScheme.error)
            Card(Modifier.fillMaxWidth()) {
                Text(text, Modifier.padding(16.dp), fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

// ---- logging in --------------------------------------------------------------------------

@Composable
private fun Login(model: AppModel, openBrowser: (String) -> Unit, modifier: Modifier) {
    var code by remember { mutableStateOf("") }
    Column(modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Spacer(Modifier.height(24.dp))
        Text("fedtail", style = MaterialTheme.typography.displaySmall)
        Text(stringResource(R.string.login_intro), style = MaterialTheme.typography.bodyLarge)
        OutlinedTextField(
            value = model.loginServer, onValueChange = { model.loginServer = it },
            label = { Text(stringResource(R.string.login_server)) },
            placeholder = { Text("social.example") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri,
                imeAction = ImeAction.Go),
            modifier = Modifier.fillMaxWidth())
        Button(onClick = { model.beginLogin(openBrowser) }, enabled = !model.loginBusy,
            modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.login_go))
        }
        if (model.loginWaiting) {
            HorizontalDivider()
            Text(stringResource(if (model.loginNeedsCode) R.string.login_paste
                                else R.string.login_waiting),
                style = MaterialTheme.typography.bodyMedium)
            OutlinedTextField(value = code, onValueChange = { code = it },
                label = { Text(stringResource(R.string.login_code)) }, singleLine = true,
                modifier = Modifier.fillMaxWidth())
            OutlinedButton(onClick = { model.finishLogin(code) },
                enabled = code.isNotBlank() && !model.loginBusy,
                modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.login_code_go))
            }
        }
        if (model.loginBusy) CircularProgressIndicator()
    }
}

// ---- lanes -------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Main(model: AppModel, snack: SnackbarHostState) {
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    BackHandler(enabled = drawer.isOpen) { scope.launch { drawer.close() } }
    ModalNavigationDrawer(drawerState = drawer, drawerContent = {
        ModalDrawerSheet {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(model.handle.let { if (it.isBlank()) "fedtail" else "@$it" } +
                        if (model.demo) "  · demo" else "",
                    Modifier.padding(16.dp), style = MaterialTheme.typography.titleMedium)
                model.lanes.forEach { lane ->
                    if (lane.group != null && lane.group.isNotBlank()) {
                        Text(lane.group, Modifier.padding(start = 16.dp, top = 12.dp, bottom = 4.dp),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    NavigationDrawerItem(
                        label = { Text(lane.title) },
                        badge = { if (lane.unread > 0) Badge { Text("${lane.unread}") } },
                        selected = lane.name == model.current,
                        onClick = {
                            model.showLane(lane.name)
                            scope.launch { drawer.close() }
                        },
                        modifier = Modifier.padding(horizontal = 12.dp))
                }
            }
        }
    }) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(model.title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawer.open() } }) {
                            Icon(Icons.Filled.Menu, stringResource(R.string.lanes))
                        }
                    },
                    actions = {
                        IconButton(onClick = { model.refresh() }) {
                            Icon(Icons.Filled.Refresh, stringResource(R.string.refresh))
                        }
                    })
            },
            snackbarHost = { SnackbarHost(snack) },
        ) { pad ->
            PullToRefreshBox(isRefreshing = model.refreshing, onRefresh = { model.refresh() },
                modifier = Modifier.padding(pad).fillMaxSize()) {
                LaneList(model)
            }
        }
    }
}

@Composable
private fun LaneList(model: AppModel) {
    val posts = model.posts
    val state = rememberLazyListState()
    // a lane opened anew stands on its first unread post, like the desktop (never jumps after)
    LaunchedEffect(model.opening) {
        if (posts.isEmpty()) return@LaunchedEffect
        val firstUnread = posts.indexOfFirst { it.unread }
        val target = when {
            firstUnread >= 0 -> firstUnread
            model.newestFirst -> 0
            else -> posts.size - 1
        }
        state.scrollToItem(target)
    }
    // read marks: what stood whole on screen when scrolling stopped (read.mark_read)
    LaunchedEffect(state, model.markOnScroll) {
        if (!model.markOnScroll) return@LaunchedEffect
        snapshotFlow { state.isScrollInProgress to state.layoutInfo.visibleItemsInfo.size }
            .collect { (scrolling, _) ->
                if (scrolling) return@collect
                delay(350)
                val info = state.layoutInfo
                val whole = info.visibleItemsInfo.filter {
                    it.offset >= info.viewportStartOffset &&
                        it.offset + it.size <= info.viewportEndOffset
                }.mapNotNull { it.key as? String }
                model.markRead(whole)
            }
    }
    if (posts.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(stringResource(R.string.lane_empty),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        return
    }
    LazyColumn(state = state, modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(posts, key = { it.key }) { p ->
            Column {
                model.divider?.takeIf { it.first == p.key }?.let { (_, words) ->
                    Text(words, Modifier.fillMaxWidth().padding(vertical = 4.dp, horizontal = 16.dp),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary)
                }
                PostCard(p)
            }
        }
    }
}

private val timeOnly = DateTimeFormatter.ofPattern("HH:mm")
private val dayAndTime = DateTimeFormatter.ofPattern("dd.MM HH:mm")

private fun shownTime(iso: String): String = try {
    val t = OffsetDateTime.parse(iso).atZoneSameInstant(ZoneId.systemDefault())
    if (t.toLocalDate() == LocalDate.now()) t.format(timeOnly) else t.format(dayAndTime)
} catch (e: Exception) {
    ""
}

@Composable
private fun PostCard(p: PostItem) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
        // unread: a bar of the theme's accent on the left, as the desktop's themes do
        Box(Modifier.width(3.dp).height(48.dp).background(
            if (p.unread) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.surface))
        Card(Modifier.fillMaxWidth().padding(start = 4.dp)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (p.sharedBy.isNotBlank()) {
                    Text(stringResource(R.string.shared_by, p.sharedBy),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(p.name, fontWeight = FontWeight.SemiBold, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    Spacer(Modifier.width(6.dp))
                    Text("@" + p.handle, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    Text(shownTime(p.created), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (p.contextText.isNotBlank()) {
                    Text("↳ @${p.contextHandle}: ${p.contextText}", maxLines = 2,
                        overflow = TextOverflow.Ellipsis, fontStyle = FontStyle.Italic,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (p.warning.isNotBlank()) {
                    Text("⚠ " + p.warning, style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.error)
                }
                Text(p.text, style = MaterialTheme.typography.bodyMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (p.alias.isNotBlank()) {
                        Text("#" + p.alias, style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary)
                    }
                    Text("💬 ${p.replies}   ↻ ${p.shares}   ★ ${p.likes}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
