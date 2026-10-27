package online.dmesg.fedtail

import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.unit.Dp
import androidx.compose.runtime.SideEffect
import androidx.compose.material3.VerticalDivider
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Switch
import androidx.compose.material3.AssistChip
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import coil.compose.AsyncImage
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.offset
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.material.icons.filled.Delete
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
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun App(model: AppModel, openBrowser: (String) -> Unit, share: (String) -> Unit = {}) {
    val snack = remember { SnackbarHostState() }
    LaunchedEffect(model.message) {
        model.message?.let {
            snack.showSnackbar(it)
            model.message = null
        }
    }
    // the lane's and the thread's place in their lists outlive what opens over them
    // (the editor, a picture): back there, they stand where they stood
    val laneState = rememberLazyListState()
    val threadState = rememberLazyListState()
    SideEffect { model.browse = openBrowser }
    AskDialogs(model)
    when (val s = model.screen) {
        Screen.Starting -> Centered { Starting() }
        is Screen.Failed -> Problem(s.text)
        Screen.Login -> Scaffold(snackbarHost = { SnackbarHost(snack) }) { pad ->
            Login(model, openBrowser, Modifier.padding(pad))
        }
        Screen.Main -> BoxWithConstraints(Modifier.fillMaxSize()) {
            val cols = columnsFor(model.layoutPref, maxWidth)
            SideEffect { model.columns = cols }
            LaunchedEffect(cols) { if (cols > 1) model.openStartLane() }
            BackHandler(enabled = model.place != null || (cols == 1 && model.current != null)) {
                model.back()
            }
            val p = model.place
            when {
                // over everything, whatever the width
                p is Place.Media -> MediaViewer(p, close = { model.back() }, openBrowser)
                p == Place.Settings -> SettingsPlace(model, snack)
                p == Place.SelfCheck -> SelfCheckPlace(model, snack, share)
                p == Place.Config -> ConfigPlace(model, snack)
                p == Place.Sync -> SyncPlace(model, snack, openBrowser)
                cols == 1 -> when (p) {
                    null -> if (model.current == null) HubScreen(model, snack)
                            else LaneScreen(model, snack, openBrowser, laneState)
                    else -> SidePlace(model, p, snack, openBrowser, threadState)
                }
                else -> Columns(model, snack, openBrowser, laneState, cols, p, threadState)
            }
        }
    }
}

/** How many columns: phone.layout, and what the width fits (a forced count only if it does). */
fun columnsFor(pref: String, width: Dp): Int {
    val fits = when {
        width >= 900.dp -> 3
        width >= 560.dp -> 2
        else -> 1
    }
    return when (pref) {
        "one" -> 1
        "two" -> minOf(2, fits)
        "three" -> fits
        else -> when {  // auto: three only on a wide tablet, two from a phone on its side up
            width >= 1000.dp -> 3
            width >= 600.dp -> 2
            else -> 1
        }
    }
}

/**
 * A tablet (or a phone on its side): the overview, the lane and — on a wide screen — the
 * thread side by side, as the desktop's columns. The editor opens where the thread would.
 */
@Composable
private fun Columns(
    model: AppModel, snack: SnackbarHostState, openBrowser: (String) -> Unit,
    laneState: LazyListState, cols: Int, p: Place?, threadState: LazyListState,
) {
    Row(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Box(Modifier.width(if (cols >= 3) 300.dp else 320.dp).fillMaxHeight()) {
            HubScreen(model, snack, pane = true)
        }
        VerticalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        val side = p != null
        Box(Modifier.weight(1f).fillMaxHeight()) {
            when {
                cols == 2 && p != null -> SidePlace(model, p, snack, openBrowser, threadState)
                model.current != null -> LaneScreen(model, snack, openBrowser, laneState, pane = true)
                else -> Hint(stringResource(R.string.pick_lane))
            }
        }
        if (cols >= 3) {
            VerticalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Box(Modifier.width(420.dp).fillMaxHeight()) {
                if (side && p != null) SidePlace(model, p, snack, openBrowser, threadState)
                else Hint(stringResource(R.string.pick_post))
            }
        }
    }
}

/** What opens over the lane — beside it, on a wide screen. */
@Composable
private fun SidePlace(
    model: AppModel, p: Place, snack: SnackbarHostState, openBrowser: (String) -> Unit,
    threadState: LazyListState,
) {
    when (p) {
        is Place.Thread -> ThreadPlace(model, snack, openBrowser, threadState)
        is Place.Compose -> ComposePlace(model, p, snack)
        is Place.Page -> PagePlace(model, p, snack, openBrowser)
        is Place.Profile -> ProfilePlace(model, p, snack, openBrowser)
        Place.Menu -> PlacesMenuPlace(model, snack)
        else -> {}
    }
}

@Composable
private fun Hint(text: String) {
    Box(Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
        Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyMedium)
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
fun PlaceScaffold(
    title: String, model: AppModel, snack: SnackbarHostState,
    actions: @Composable () -> Unit = {},
    onRefresh: (() -> Unit)? = null, // ⟳ in the bar: the place asked anew, the server too
    content: @Composable (Modifier) -> Unit,
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
                actions = {
                    onRefresh?.let { r ->
                        IconButton(onClick = r) {
                            ThemedIcon("refresh", Icons.Filled.Refresh, stringResource(R.string.refresh))
                        }
                    }
                    actions()
                })
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

// ---- a thread ----------------------------------------------------------------------------

@Composable
private fun ThreadPlace(
    model: AppModel, snack: SnackbarHostState, openBrowser: (String) -> Unit, state: LazyListState,
) {
    val focus = (model.place as? Place.Thread)?.focus
    val act = model.cardActions(openBrowser, cwOpen = model.threadCwOpen)
    val root = model.threadPosts.firstOrNull()
    val head = model.threadHead
    PlaceScaffold(stringResource(R.string.thread) + (root?.alias?.takeIf { it.isNotBlank() }
        ?.let { " #$it" } ?: ""), model, snack, onRefresh = { model.refreshTop() }, actions = {
        // every warning of the thread open at once (and closed again)
        if (model.threadPosts.any { it.warning.isNotBlank() }) {
            val cwWords = stringResource(R.string.open_warnings)
            IconButton(onClick = { model.threadCwOpen = !model.threadCwOpen },
                modifier = Modifier.semantics { contentDescription = cwWords }) {
                Text(if (model.threadCwOpen) "⚠✓" else "⚠", fontSize = 16.sp)
            }
        }
    }) { mod ->
        Box(mod.background(MaterialTheme.colorScheme.surface)) {
            // aimed when opened (on the post tapped) or after a reply (on the reply); coming
            // back from the editor or a picture it stays where it was
            LaunchedEffect(model.threadOpening) {
                if (model.threadOpening == model.threadAimed) return@LaunchedEffect
                val want = model.threadAimAt ?: focus
                val i = model.threadPosts.indexOfFirst { it.sid == want || it.id == want }
                    .takeIf { it >= 0 } ?: model.threadPosts.indexOfFirst { it.sid == focus }
                // the head is the list's first item: every post one further
                if (i >= 0) state.scrollToItem(i + if (model.threadHead != null) 1 else 0)
                model.threadAimed = model.threadOpening
                model.threadAimAt = null
            }
            MarkWhileScrolling(state, model.markOnScroll) { model.markRead(it, inThread = true) }
            if (model.threadPosts.isEmpty()) Centered { CircularProgressIndicator() }
            else PostList(model.threadPosts, state, null, act, model.hideSensitive,
                thread = true, focus = focus,
                header = head?.let { h -> @Composable { ThreadHead(h) { model.toggleThreadSub() } } })
        }
    }
}

/** The windows' head over a thread: how many answers and its #id, why it reaches me
 *  when not followed, and Follow — a button that says what it is now. */
@Composable
private fun ThreadHead(head: org.json.JSONObject, onSub: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                head.optString("title").takeIf { it.isNotBlank() }?.let {
                    Text(it, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, maxLines = 2,
                        overflow = TextOverflow.Ellipsis)
                }
                head.optString("info").takeIf { it.isNotBlank() }?.let {
                    Text(it, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            val on = head.optBoolean("subscribed")
            val words = head.optString("sub")
            if (on) OutlinedButton(onClick = onSub) { Text(words) }
            else Button(onClick = onSub) { Text(words) }
        }
        head.optString("via").takeIf { it.isNotBlank() }?.let {
            Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp))
        }
        HorizontalDivider(Modifier.padding(top = 8.dp), color = MaterialTheme.colorScheme.outlineVariant)
    }
}

// ---- writing -----------------------------------------------------------------------------

private val VISIBILITIES = listOf(
    "public" to R.string.vis_public, "unlisted" to R.string.vis_unlisted,
    "followers" to R.string.vis_followers, "direct" to R.string.vis_direct)

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ComposePlace(model: AppModel, place: Place.Compose, snack: SnackbarHostState) {
    val title = stringResource(when {
        model.editId != null -> R.string.edit_post
        place.replyTo == null -> R.string.new_post
        else -> R.string.reply
    })
    val pick = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(maxOf(2, model.maxMedia()))) { uris ->
        if (uris.isNotEmpty()) model.attach(uris)
    }
    val editing = model.editId != null
    // kept as it goes (post.drafts_autosave): a moment after the typing stops
    LaunchedEffect(model.composeText, model.composeCw, model.composeCwOn, model.composeVisibility,
        model.composeLang, model.pollOn, model.pollOptions, model.composeSensitive) {
        delay(1500)
        model.saveDraft()
    }
    val context = androidx.compose.ui.platform.LocalContext.current
    PlaceScaffold(title, model, snack, actions = {
        IconButton(onClick = { model.discard() }) {
            Icon(Icons.Filled.Delete, stringResource(R.string.discard))
        }
        val previewWords = stringResource(R.string.preview)
        IconButton(onClick = { model.preview() }, enabled = model.composeText.isNotBlank(),
            modifier = Modifier.semantics { contentDescription = previewWords }) {
            Text("👁", fontSize = 18.sp)
        }
        IconButton(onClick = { model.send() },
            enabled = !model.sending && model.uploading == 0 && model.composeText.isNotBlank()) {
            ThemedIcon("send", Icons.AutoMirrored.Filled.Send, stringResource(R.string.send))
        }
    }) { mod ->
        Column(mod.padding(16.dp).imePadding().verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            place.replyTo?.let {
                Text("↳ @${it.handle}: ${it.text}", maxLines = 3, overflow = TextOverflow.Ellipsis,
                    fontStyle = FontStyle.Italic, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (model.quoteOf.isNotBlank()) {
                Text("❝ " + model.quoteOf, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (!editing) {
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
            }
            val from = model.fromAccounts()
            if (from.isNotEmpty() && !editing && place.replyTo == null) {
                Row(Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    from.forEachIndexed { i, (key, words) ->
                        FilterChip(selected = (model.composeFrom ?: from.first().first) == key,
                            onClick = { model.composeFrom = key }, label = { Text(words) })
                    }
                }
            }
            if (model.composeCwOn) {
                OutlinedTextField(value = model.composeCw, onValueChange = { model.composeCw = it },
                    label = { Text(stringResource(R.string.cw_label)) }, singleLine = true,
                    modifier = Modifier.fillMaxWidth())
            }
            // the text with its cursor: what is typed right before it is completed
            var field by remember { mutableStateOf(TextFieldValue(model.composeText,
                TextRange(model.composeText.length))) }
            if (field.text != model.composeText) {  // set from outside (a quote, a redraft)
                field = TextFieldValue(model.composeText, TextRange(model.composeText.length))
            }
            var offer by remember { mutableStateOf<Pair<String, List<Pair<String, String>>>?>(null) }
            LaunchedEffect(field.text, field.selection) {
                offer = null
                if (!field.selection.collapsed) return@LaunchedEffect
                val before = field.text.substring(0, field.selection.start)
                if (before.isEmpty() || before.last().isWhitespace()) return@LaunchedEffect
                delay(200)
                val got = Core.complete(before.substringAfterLast('\n'))
                val items = got.optJSONArray("items") ?: return@LaunchedEffect
                val list = (0 until items.length()).map {
                    val o = items.getJSONObject(it)
                    o.optString("insert") to o.optString("label")
                }
                if (list.isNotEmpty()) offer = got.optString("word") to list
            }
            offer?.let { (word, items) ->
                Row(Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items.forEach { (insert, label) ->
                        AssistChip(onClick = {
                            val end = field.selection.start
                            val start = (end - word.length).coerceAtLeast(0)
                            val text = field.text.substring(0, start) + insert + " " + field.text.substring(end)
                            val at = start + insert.length + 1
                            field = TextFieldValue(text, TextRange(at))
                            model.composeText = text
                            offer = null
                        }, label = { Text(label, maxLines = 1) })
                    }
                }
            }
            OutlinedTextField(value = field, onValueChange = { field = it; model.composeText = it.text },
                modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp),
                placeholder = { Text(stringResource(R.string.write_here)) },
                supportingText = {
                    val n = model.composeText.length + (if (model.composeCwOn) model.composeCw.length else 0)
                    Column {
                        Text("$n / ${model.charLimit()}",
                            color = if (n > model.charLimit()) MaterialTheme.colorScheme.error
                                    else MaterialTheme.colorScheme.onSurfaceVariant)
                        // a chain's parts, "#CamelCase for screen readers" — the windows' words
                        if (model.composeHints.isNotBlank()) Text(model.composeHints,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (model.composeNewcomers.isNotBlank()) Text(model.composeNewcomers,
                            color = MaterialTheme.colorScheme.error)
                    }
                })
            LaunchedEffect(model.composeText, model.composeCw, model.composeCwOn,
                model.composeVisibility) {
                delay(400)  // as it is typed: asked once the fingers pause
                model.checkCompose()
            }
            // what goes with the words: a warning, pictures, a poll, the language
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = model.composeCwOn, onClick = { model.composeCwOn = !model.composeCwOn },
                    label = { Text(stringResource(R.string.cw_add)) })
                if (!editing) {
                    // "send later": the server keeps it until then (scheduled_at)
                    FilterChip(selected = model.composeWhen.isNotBlank(), onClick = {
                        if (model.composeWhen.isNotBlank()) model.composeWhen = ""
                        else pickWhen(context) { model.composeWhen = it }
                    }, label = {
                        Text(if (model.composeWhen.isBlank()) stringResource(R.string.send_later)
                             else "⏰ " + model.composeWhen.replace("T", " "))
                    })
                    FilterChip(selected = false, enabled = !model.pollOn &&
                            model.attachments.size < model.maxMedia(),
                        onClick = { pick.launch(PickVisualMediaRequest(
                            ActivityResultContracts.PickVisualMedia.ImageAndVideo)) },
                        label = { Text(stringResource(R.string.attach)) })
                    FilterChip(selected = model.pollOn, enabled = model.attachments.isEmpty(),
                        onClick = { model.pollOn = !model.pollOn },
                        label = { Text(stringResource(R.string.poll)) })
                    LanguagePick(model)
                }
            }
            if (model.uploading > 0) {
                Row(verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text(stringResource(R.string.uploading), style = MaterialTheme.typography.bodySmall)
                }
            }
            model.attachments.forEach { a -> AttachmentRow(model, a, editing) }
            if (model.attachments.isNotEmpty() && !editing) {
                Row(Modifier.fillMaxWidth().clickable { model.composeSensitive = !model.composeSensitive },
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.mark_sensitive), Modifier.weight(1f))
                    Switch(checked = model.composeSensitive, onCheckedChange = { model.composeSensitive = it })
                }
            }
            if (model.pollOn && !editing) PollEditor(model)
            if (model.composeHint.isNotBlank()) Text(model.composeHint,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (model.sending) CircularProgressIndicator()
        }
    }
    model.previewing?.let { pv -> PreviewDialog(model, pv) }
}

/** The post as it will read (the core's preview, Qt's): who sees it, the parts, then
 *  back to the text or send. */
@Composable
private fun PreviewDialog(model: AppModel, pv: org.json.JSONObject) {
    val parts = pv.optJSONArray("parts") ?: org.json.JSONArray()
    androidx.compose.material3.AlertDialog(
        onDismissRequest = { model.previewing = null },
        title = { Text(pv.optString("title")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (pv.optString("head").isNotBlank()) Text(pv.optString("head"),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (pv.optString("cw").isNotBlank()) Text("⚠ " + pv.optString("cw"),
                    fontWeight = FontWeight.Medium)
                for (i in 0 until parts.length()) {
                    if (i > 0) HorizontalDivider()
                    HtmlText(parts.optString(i), onLink = {})
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { model.previewing = null; model.send() }) { Text(pv.optString("send")) }
        },
        dismissButton = {
            TextButton(onClick = { model.previewing = null }) { Text(pv.optString("back")) }
        })
}

/** A date, then a time — the phone's own pickers → "2026-10-26T09:30" (local). */
private fun pickWhen(context: android.content.Context, done: (String) -> Unit) {
    val now = java.util.Calendar.getInstance().apply { add(java.util.Calendar.HOUR_OF_DAY, 1) }
    android.app.DatePickerDialog(context, { _, y, m, d ->
        android.app.TimePickerDialog(context, { _, h, min ->
            done("%04d-%02d-%02dT%02d:%02d".format(y, m + 1, d, h, min))
        }, now.get(java.util.Calendar.HOUR_OF_DAY), 0, true).show()
    }, now.get(java.util.Calendar.YEAR), now.get(java.util.Calendar.MONTH),
        now.get(java.util.Calendar.DAY_OF_MONTH)).show()
}

@Composable
private fun LanguagePick(model: AppModel) {
    var open by remember { mutableStateOf(false) }
    val langs = model.languages()
    if (langs.isEmpty()) return
    var asking by remember { mutableStateOf(false) }
    Box {
        FilterChip(selected = model.composeLang.isNotBlank(), onClick = { open = true },
            label = { Text(langs.firstOrNull { it.first == model.composeLang }?.second
                ?: model.composeLang.ifBlank { stringResource(R.string.language) }) })
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            langs.forEach { (code, words) ->
                DropdownMenuItem(text = { Text(words) },
                    onClick = { open = false; model.composeLang = code })
            }
            // "Another language…": a code typed, kept on the list from then on
            model.otherLanguageWords()?.let { words ->
                DropdownMenuItem(text = { Text(words) }, onClick = { open = false; asking = true })
            }
        }
    }
    if (asking) {
        var code by remember { mutableStateOf("") }
        androidx.compose.material3.AlertDialog(onDismissRequest = { asking = false },
            title = { Text(stringResource(R.string.lang_other_title)) },
            text = {
                OutlinedTextField(value = code, onValueChange = { code = it.lowercase() },
                    singleLine = true, label = { Text(stringResource(R.string.lang_other_ask)) })
            },
            confirmButton = {
                TextButton(onClick = { asking = false; model.addLanguage(code) },
                    enabled = code.isNotBlank()) { Text(stringResource(android.R.string.ok)) }
            },
            dismissButton = {
                TextButton(onClick = { asking = false }) { Text(stringResource(R.string.cancel)) }
            })
    }
}

@Composable
private fun AttachmentRow(model: AppModel, a: Attachment, editing: Boolean) {
    val pickCover = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) model.setCover(a, uri)
    }
    val moving = a.kind == "video" || a.kind == "audio"
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
        // a picture: a tap says where its previews centre on (the focus point)
        Box(Modifier.size(96.dp).clip(RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .then(if (moving) Modifier else Modifier.pointerInput(a.token, a.id) {
                detectTapGestures { pos ->
                    val x = (pos.x / size.width) * 2f - 1f
                    val y = 1f - (pos.y / size.height) * 2f
                    model.setFocus(a, x.coerceIn(-1f, 1f), y.coerceIn(-1f, 1f))
                }
            }), contentAlignment = Alignment.Center) {
            val shown = a.coverPreview.ifBlank { a.preview }
            if (shown.isNotBlank()) {
                AsyncImage(model = shown, contentDescription = a.alt.ifBlank { null },
                    contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
            }
            if (moving) Text("▶", color = MaterialTheme.colorScheme.onSurface)
            a.focus?.let { (fx, fy) ->
                BoxWithConstraints(Modifier.fillMaxSize()) {
                    Box(Modifier.offset(x = maxWidth * ((fx + 1f) / 2f) - 6.dp,
                        y = maxHeight * ((1f - fy) / 2f) - 6.dp).size(12.dp).clip(CircleShape)
                        .background(MaterialTheme.colorScheme.primary))
                }
            }
        }
        Column(Modifier.weight(1f)) {
            OutlinedTextField(value = a.alt, onValueChange = { model.describe(a, it) },
                label = { Text(stringResource(R.string.alt_label)) }, minLines = 2,
                modifier = Modifier.fillMaxWidth())
            Row {
                if (moving && !editing) TextButton(onClick = {
                    pickCover.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }) { Text(stringResource(if (a.cover.isBlank()) R.string.cover else R.string.cover_set)) }
                if (!editing) TextButton(onClick = { model.detach(a) }) { Text(stringResource(R.string.detach)) }
            }
            if (!moving) Text(stringResource(R.string.focus_tip), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun PollEditor(model: AppModel) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        model.pollOptions.forEachIndexed { i, text ->
            OutlinedTextField(value = text, singleLine = true,
                onValueChange = { v -> model.pollOptions = model.pollOptions.toMutableList().also { it[i] = v } },
                label = { Text(stringResource(R.string.poll_option, i + 1)) },
                modifier = Modifier.fillMaxWidth())
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (model.pollOptions.size < model.maxOptions()) {
                TextButton(onClick = { model.pollOptions = model.pollOptions + "" }) {
                    Text(stringResource(R.string.poll_add))
                }
            }
            if (model.pollOptions.size > 2) {
                TextButton(onClick = { model.pollOptions = model.pollOptions.dropLast(1) }) {
                    Text(stringResource(R.string.poll_remove))
                }
            }
        }
        Row(Modifier.fillMaxWidth().clickable { model.pollMultiple = !model.pollMultiple },
            verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.poll_multiple), Modifier.weight(1f))
            Switch(checked = model.pollMultiple, onCheckedChange = { model.pollMultiple = it })
        }
        Row(Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            model.pollLengths().forEach { (secs, words) ->
                FilterChip(selected = model.pollExpires == secs, onClick = { model.pollExpires = secs },
                    label = { Text(words) })
            }
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
                OutlinedButton(onClick = { model.back(); model.openSettings("sync") }) {
                    Text(stringResource(R.string.settings))
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
