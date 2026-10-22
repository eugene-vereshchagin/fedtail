package online.dmesg.fedtail

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Badge
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
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
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextStyle
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
        Screen.Main -> {
            BackHandler(enabled = model.place != null) { model.back() }
            when (val p = model.place) {
                null -> Main(model, snack)
                is Place.Thread -> ThreadPlace(model, snack)
                is Place.Compose -> ComposePlace(model, p, snack)
                Place.Config -> ConfigPlace(model, snack)
                Place.Sync -> SyncPlace(model, snack, openBrowser)
            }
        }
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

/** A place over the lane: a bar with ← and a title, maybe an action on the right. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PlaceScaffold(
    title: String, model: AppModel, snack: SnackbarHostState,
    actions: @Composable () -> Unit = {}, content: @Composable (Modifier) -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = { model.back() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back))
                    }
                },
                actions = { actions() })
        },
        snackbarHost = { SnackbarHost(snack) },
    ) { pad -> content(Modifier.padding(pad).fillMaxSize()) }
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
                HorizontalDivider(Modifier.padding(vertical = 8.dp))
                NavigationDrawerItem(label = { Text(stringResource(R.string.sync)) },
                    selected = false, modifier = Modifier.padding(horizontal = 12.dp),
                    onClick = { scope.launch { drawer.close() }; model.openSync() })
                NavigationDrawerItem(label = { Text(stringResource(R.string.config)) },
                    selected = false, modifier = Modifier.padding(horizontal = 12.dp),
                    onClick = { scope.launch { drawer.close() }; model.openConfig() })
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
            floatingActionButton = {
                FloatingActionButton(onClick = { model.compose(null) }) {
                    Icon(Icons.Filled.Edit, stringResource(R.string.write))
                }
            },
            snackbarHost = { SnackbarHost(snack) },
        ) { pad ->
            PullToRefreshBox(isRefreshing = model.refreshing, onRefresh = { model.refresh() },
                modifier = Modifier.padding(pad).fillMaxSize()) {
                val state = rememberLazyListState()
                LaunchedEffect(model.opening) { aim(state, model.posts, model.newestFirst) }
                MarkWhileScrolling(state, model.markOnScroll) { model.markRead(it) }
                PostList(model.posts, state, model.divider, onOpen = { model.openThread(it.sid) },
                    onReply = { model.compose(it) }, onLike = { model.like(it) })
            }
        }
    }
}

/** A list opened anew stands on its first unread post, like the desktop; never jumps after. */
private suspend fun aim(state: LazyListState, posts: List<PostItem>, newestFirst: Boolean) {
    if (posts.isEmpty()) return
    val firstUnread = posts.indexOfFirst { it.unread }
    state.scrollToItem(when {
        firstUnread >= 0 -> firstUnread
        newestFirst -> 0
        else -> posts.size - 1
    })
}

/** Read marks: what stood whole on screen when scrolling stopped (read.mark_read). */
@Composable
private fun MarkWhileScrolling(state: LazyListState, on: Boolean, mark: (List<String>) -> Unit) {
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

@Composable
private fun PostList(
    posts: List<PostItem>, state: LazyListState, divider: Pair<String, String>?,
    onOpen: (PostItem) -> Unit, onReply: (PostItem) -> Unit, onLike: (PostItem) -> Unit,
    focus: String? = null,
) {
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
                divider?.takeIf { it.first == p.key }?.let { (_, words) ->
                    Text(words, Modifier.fillMaxWidth().padding(vertical = 4.dp, horizontal = 16.dp),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary)
                }
                PostCard(p, focused = p.sid == focus, onOpen = { onOpen(p) },
                    onReply = { onReply(p) }, onLike = { onLike(p) })
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
private fun PostCard(
    p: PostItem, focused: Boolean, onOpen: () -> Unit, onReply: () -> Unit, onLike: () -> Unit,
) {
    // a thread's depth as an indent, up to a limit: deeper ones say /N instead
    val indent = (minOf(p.depth, 6) * 12).dp
    Row(Modifier.fillMaxWidth().padding(start = 8.dp + indent, end = 8.dp)) {
        // unread: a bar of the theme's accent on the left, as the desktop's themes do
        Box(Modifier.width(3.dp).height(48.dp).background(
            if (p.unread) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.surface))
        Card(Modifier.fillMaxWidth().padding(start = 4.dp).clickable(onClick = onOpen)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (p.sharedBy.isNotBlank()) {
                    Text(stringResource(R.string.shared_by, p.sharedBy),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    p.number?.let {
                        Text("/$it ", style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary)
                    }
                    Text(p.name, fontWeight = if (focused) FontWeight.Bold else FontWeight.SemiBold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false))
                    Spacer(Modifier.width(6.dp))
                    Text("@" + p.handle, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    Text(shownTime(p.created), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (p.contextText.isNotBlank() && p.number == null) {
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
                Row(verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (p.alias.isNotBlank()) {
                        Text("#" + p.alias, style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary)
                    }
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = onReply) {
                        Text("💬 ${p.replies}", style = MaterialTheme.typography.labelMedium)
                    }
                    Text("↻ ${p.shares}", style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    TextButton(onClick = onLike) {
                        Text((if (p.liked) "★ " else "☆ ") + p.likes,
                            style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
        }
    }
}

// ---- a thread ----------------------------------------------------------------------------

@Composable
private fun ThreadPlace(model: AppModel, snack: SnackbarHostState) {
    val focus = (model.place as? Place.Thread)?.focus
    PlaceScaffold(stringResource(R.string.thread), model, snack) { mod ->
        Box(mod) {
            val state = rememberLazyListState()
            LaunchedEffect(model.threadOpening) {
                val i = model.threadPosts.indexOfFirst { it.sid == focus }
                if (i >= 0) state.scrollToItem(i)
            }
            MarkWhileScrolling(state, model.markOnScroll) { model.markRead(it, inThread = true) }
            if (model.threadPosts.isEmpty()) Centered { CircularProgressIndicator() }
            else PostList(model.threadPosts, state, null, focus = focus,
                onOpen = {}, onReply = { model.compose(it) }, onLike = { model.like(it) })
        }
    }
}

// ---- writing -----------------------------------------------------------------------------

private val VISIBILITIES = listOf(
    "public" to R.string.vis_public, "unlisted" to R.string.vis_unlisted,
    "followers" to R.string.vis_followers, "direct" to R.string.vis_direct)

@Composable
private fun ComposePlace(model: AppModel, place: Place.Compose, snack: SnackbarHostState) {
    val title = stringResource(if (place.replyTo == null) R.string.new_post else R.string.reply)
    PlaceScaffold(title, model, snack, actions = {
        IconButton(onClick = { model.send() }, enabled = !model.sending && model.composeText.isNotBlank()) {
            Icon(Icons.AutoMirrored.Filled.Send, stringResource(R.string.send))
        }
    }) { mod ->
        Column(mod.padding(16.dp).imePadding(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            place.replyTo?.let {
                Text("↳ @${it.handle}: ${it.text}", maxLines = 3, overflow = TextOverflow.Ellipsis,
                    fontStyle = FontStyle.Italic, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                VISIBILITIES.forEach { (word, label) ->
                    FilterChip(selected = model.composeVisibility == word,
                        onClick = { model.composeVisibility = word },
                        label = { Text(stringResource(label)) })
                }
            }
            if (place.replyTo != null && model.composeVisibility == null) {
                Text(stringResource(R.string.vis_as_parent), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            OutlinedTextField(value = model.composeText, onValueChange = { model.composeText = it },
                modifier = Modifier.fillMaxWidth().weight(1f),
                placeholder = { Text(stringResource(R.string.write_here)) })
            if (model.sending) CircularProgressIndicator()
        }
    }
}

// ---- the config file, edited here --------------------------------------------------------

@Composable
private fun ConfigPlace(model: AppModel, snack: SnackbarHostState) {
    PlaceScaffold(stringResource(R.string.config), model, snack, actions = {
        IconButton(onClick = { model.saveConfig() }, enabled = !model.saving) {
            Icon(Icons.Filled.Check, stringResource(R.string.save))
        }
    }) { mod ->
        Column(mod.padding(8.dp).imePadding()) {
            model.configError?.let {
                Text(it, color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(8.dp))
            }
            OutlinedTextField(value = model.configText, onValueChange = { model.configText = it },
                modifier = Modifier.fillMaxWidth().weight(1f),
                textStyle = TextStyle(fontFamily = FontFamily.Monospace,
                    fontSize = MaterialTheme.typography.bodySmall.fontSize))
        }
    }
}

// ---- sync --------------------------------------------------------------------------------

@Composable
private fun SyncPlace(model: AppModel, snack: SnackbarHostState, openBrowser: (String) -> Unit) {
    val clipboard = LocalClipboardManager.current
    var code by remember { mutableStateOf("") }
    var key by remember { mutableStateOf("") }
    var done by remember { mutableStateOf("") }
    val info = model.syncInfo
    PlaceScaffold(stringResource(R.string.sync), model, snack) { mod ->
        Column(mod.padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (info == null) {
                CircularProgressIndicator()
                return@Column
            }
            if (!info.optBoolean("enabled")) {
                Text(stringResource(R.string.sync_off), style = MaterialTheme.typography.bodyMedium)
                OutlinedButton(onClick = { model.back(); model.openConfig() }) {
                    Text(stringResource(R.string.config))
                }
            } else {
                val last = info.optJSONObject("last")
                Fact(stringResource(R.string.sync_where),
                    info.optString("backend") + " " + info.optString("where"))
                Fact(stringResource(R.string.sync_login), info.optString("login").ifBlank { "—" })
                Fact(stringResource(R.string.sync_key_id), info.optString("key").ifBlank { "—" })
                Fact(stringResource(R.string.sync_pending), "${info.optInt("pending")}")
                Fact(stringResource(R.string.sync_last), listOfNotNull(
                    last?.optString("at")?.takeIf { it.isNotBlank() },
                    last?.optString("error")?.takeIf { it.isNotBlank() }).joinToString("\n")
                    .ifBlank { "—" })
                Button(onClick = { model.syncNow { done = it } }, enabled = !model.syncBusy,
                    modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.sync_now)) }
                if (done.isNotBlank()) Text(stringResource(R.string.sync_done, done))
                if (info.optString("backend") == "server") {
                    HorizontalDivider()
                    OutlinedButton(onClick = { model.syncLogin(openBrowser) },
                        modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.sync_login_go))
                    }
                    if (model.syncLoginWaiting) {
                        OutlinedTextField(value = code, onValueChange = { code = it },
                            label = { Text(stringResource(R.string.login_code)) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth())
                        OutlinedButton(onClick = { model.syncLoginCode(code) },
                            enabled = code.isNotBlank()) { Text(stringResource(R.string.login_code_go)) }
                    }
                }
            }
            HorizontalDivider()
            Text(stringResource(R.string.sync_key_intro), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            OutlinedButton(onClick = { model.syncShowKey() }, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.sync_key_show))
            }
            if (model.syncKeyShown.isNotBlank()) {
                Text(model.syncKeyShown, fontFamily = FontFamily.Monospace)
                TextButton(onClick = { clipboard.setText(AnnotatedString(model.syncKeyShown)) }) {
                    Text(stringResource(R.string.copy))
                }
            }
            OutlinedTextField(value = key, onValueChange = { key = it },
                label = { Text(stringResource(R.string.sync_key_paste)) },
                modifier = Modifier.fillMaxWidth())
            OutlinedButton(onClick = { model.syncJoin(key); key = "" }, enabled = key.isNotBlank(),
                modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.sync_join)) }
        }
    }
}

@Composable
private fun Fact(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}
