package online.dmesg.fedtail

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.fromHtml
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import org.json.JSONArray
import org.json.JSONObject

/*
 * The places of the windows' ≡ menu (common/places.py) — search, lists, filters, the
 * server, help… — drawn from the same data the browser page gets; a profile; the core's
 * questions as dialogs. Each place's logic is the desktop's: the phone only lays it out.
 */

/** The core's questions — "sure?", one of a few answers, a line to type — over everything. */
@Composable
fun AskDialogs(model: AppModel) {
    when (val a = model.asking) {
        null -> {}
        is Asking.Confirm -> AlertDialog(
            onDismissRequest = { model.asking = null },
            title = if (a.title.isNotBlank()) { { Text(a.title) } } else null,
            text = { Text(a.text) },
            confirmButton = {
                TextButton(onClick = { model.asking = null; a.yes() }) {
                    Text(a.yesLabel.ifBlank { stringResource(R.string.yes) })
                }
            },
            dismissButton = {
                TextButton(onClick = { model.asking = null }) {
                    Text(a.noLabel.ifBlank { stringResource(R.string.cancel) })
                }
            })
        is Asking.Choose -> {
            var ticked by remember(a) { mutableStateOf(false) }
            AlertDialog(
                onDismissRequest = { model.asking = null },
                title = if (a.title.isNotBlank()) { { Text(a.title) } } else null,
                text = {
                    Column(Modifier.verticalScroll(rememberScrollState())) {
                        if (a.text.isNotBlank()) Text(a.text, Modifier.padding(bottom = 8.dp))
                        a.options.forEach { (key, label) ->
                            Text(label, Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                                .clickable { model.asking = null; a.pick(key, ticked) }
                                .padding(horizontal = 8.dp, vertical = 12.dp),
                                style = MaterialTheme.typography.bodyLarge)
                        }
                        if (a.check.isNotBlank()) {
                            Row(verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.clickable { ticked = !ticked }) {
                                Checkbox(checked = ticked, onCheckedChange = { ticked = it })
                                Text(a.check)
                            }
                        }
                    }
                },
                confirmButton = {},
                dismissButton = {
                    TextButton(onClick = { model.asking = null }) { Text(stringResource(R.string.cancel)) }
                })
        }
        is Asking.Text -> {
            var text by remember(a) { mutableStateOf(a.text) }
            AlertDialog(
                onDismissRequest = { model.asking = null },
                title = if (a.title.isNotBlank()) { { Text(a.title) } } else null,
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (a.question.isNotBlank()) Text(a.question)
                        OutlinedTextField(value = text, onValueChange = { text = it },
                            modifier = Modifier.fillMaxWidth())
                    }
                },
                confirmButton = {
                    TextButton(onClick = { model.asking = null; a.done(text) }) {
                        Text(stringResource(R.string.ok))
                    }
                },
                dismissButton = {
                    TextButton(onClick = { model.asking = null }) { Text(stringResource(R.string.cancel)) }
                })
        }
    }
}

/** HTML made safe by the core (help, the server's about, a note): links tappable. */
@Composable
fun HtmlText(html: String, onLink: (String) -> Unit, modifier: Modifier = Modifier) {
    val color = MaterialTheme.colorScheme.primary
    val text = remember(html, color) {
        try {
            AnnotatedString.fromHtml(html.trim(), TextLinkStyles(SpanStyle(color = color))) { link ->
                (link as? LinkAnnotation.Url)?.url?.let(onLink)
            }
        } catch (e: Exception) {
            AnnotatedString(html)
        }
    }
    Text(text, modifier, style = MaterialTheme.typography.bodyMedium)
}

/** A face by its address, or the first letter on the person's colour. */
@Composable
fun Face(url: String, name: String, handle: String, size: Int) {
    Box(Modifier.size(size.dp).clip(CircleShape).background(faceColor(handle)),
        contentAlignment = Alignment.Center) {
        Text(name.take(1).uppercase(), color = Color.White, fontWeight = FontWeight.SemiBold,
            fontSize = (size * 0.42).sp)
        if (url.isNotBlank()) {
            AsyncImage(model = ImageRequest.Builder(LocalContext.current).data(url).crossfade(true).build(),
                contentDescription = null, contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize())
        }
    }
}

// ---- the places' list (≡) ------------------------------------------------------------------

@Composable
fun PlacesMenuPlace(model: AppModel, snack: SnackbarHostState) {
    PlaceScaffold(stringResource(R.string.places), model, snack) { mod ->
        if (model.placeMenu.isEmpty()) {
            Box(mod, contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@PlaceScaffold
        }
        LazyColumn(mod, contentPadding = PaddingValues(vertical = 8.dp)) {
            items(model.placeMenu) { (name, title) ->
                Text(title, Modifier.fillMaxWidth().clickable { model.openPage(name) }
                    .padding(horizontal = 20.dp, vertical = 14.dp),
                    style = MaterialTheme.typography.bodyLarge)
            }
        }
    }
}

// ---- a place ------------------------------------------------------------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PagePlace(model: AppModel, p: Place.Page, snack: SnackbarHostState, openBrowser: (String) -> Unit) {
    val view = model.pages[p]
    val act = model.cardActions(openBrowser)
    val onLink: (String) -> Unit = { url ->
        if (url.startsWith("fedtail:")) model.runLink(url) else model.openLink(url, openBrowser)
    }
    PlaceScaffold(view?.title ?: "", model, snack) { mod ->
        if (view == null) {
            Box(mod, contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@PlaceScaffold
        }
        // the form's values: what the fields hold now (reset when the place comes anew)
        val values = remember(view.form) {
            mutableStateMapOf<String, Any?>().apply { view.form.forEach { put(it.name, it.value) } }
        }
        val formJson = {
            val o = JSONObject()
            view.form.forEach { f ->
                when (val v = values[f.name]) {
                    null -> {}
                    is List<*> -> o.put(f.name, JSONArray(v))
                    is JSONArray -> o.put(f.name, v)
                    else -> o.put(f.name, v)
                }
            }
            o
        }
        val press: (PlaceButton) -> Unit = { b ->
            if (b.act.size == 3 && b.act[0] == "post" && b.act[1] == "thread") model.openThread(b.act[2])
            else model.pageAct(b, formJson())
        }
        LazyColumn(mod, state = rememberLazyListState(),
            contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (view.hint.isNotBlank()) item {
                Text(view.hint, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (view.tabs.isNotEmpty()) item {
                Row(Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    view.tabs.forEach { (key, label) ->
                        FilterChip(selected = key == view.tab,
                            onClick = { model.openPage(p.name, p.arg, key) },
                            label = { Text(label) })
                    }
                }
            }
            if (view.form.isNotEmpty()) item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    view.form.forEach { f -> FormField(model, f, values) }
                    view.submit?.let { b ->
                        Button(onClick = { press(b) }) { Text(b.label) }
                    }
                }
            } else view.submit?.let { b ->
                item { Button(onClick = { press(b) }) { Text(b.label) } }
            }
            if (view.rows.isEmpty() && view.empty.isNotBlank()) item {
                Text(view.empty, Modifier.fillMaxWidth().padding(vertical = 24.dp),
                    textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            items(view.rows) { r -> PageRowView(model, r, act, press, onLink) }
            view.more?.let { b ->
                item {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                        OutlinedButton(onClick = { press(b) }) { Text(b.label) }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PageRowView(
    model: AppModel, r: PageRow, act: CardActions, press: (PlaceButton) -> Unit,
    onLink: (String) -> Unit,
) {
    val buttons: @Composable () -> Unit = {
        if (r.buttons.isNotEmpty()) FlowRow(Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End) {
            r.buttons.forEach { b ->
                TextButton(onClick = { press(b) }) {
                    Text(b.label, fontWeight = if (b.primary) FontWeight.SemiBold else FontWeight.Normal)
                }
            }
        }
    }
    when {
        r.kind == "post" && r.post != null -> Column {
            PostCard(r.post, act, model.hideSensitive)
            buttons()
        }
        r.kind == "account" && r.account != null -> Column(Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(14.dp)).background(MaterialTheme.colorScheme.surface)
            .clickable { model.openProfile(r.account.id) }.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Face(r.account.avatar, r.account.name, r.account.handle, 40)
                Column(Modifier.weight(1f)) {
                    Text(r.account.name, fontWeight = FontWeight.SemiBold, maxLines = 1,
                        overflow = TextOverflow.Ellipsis)
                    Text("@" + r.account.handle, fontSize = 13.sp, maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (r.line.isNotBlank()) Text(r.line, fontSize = 13.sp, maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            buttons()
        }
        r.kind == "heading" -> Text(r.title, Modifier.padding(top = 12.dp, start = 4.dp),
            style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
        r.kind == "html" -> Column {
            HtmlText(r.html, onLink, Modifier.fillMaxWidth().padding(horizontal = 4.dp))
            buttons()
        }
        else -> Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(start = 14.dp, end = 6.dp, top = 10.dp,
                bottom = if (r.buttons.isEmpty()) 10.dp else 2.dp)) {
            if (r.title.isNotBlank()) Text(r.title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            if (r.line.isNotBlank()) Text(r.line, fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            buttons()
        }
    }
}

/** A form's field as the windows have it: a line, lines, a box, one of, several of, a file. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FormField(model: AppModel, f: PageField, values: MutableMap<String, Any?>) {
    val tip: @Composable () -> Unit = {
        if (f.tip.isNotBlank()) Text(f.tip, style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    when (f.kind) {
        "check" -> Column {
            Row(Modifier.fillMaxWidth().clickable { values[f.name] = values[f.name] != true },
                verticalAlignment = Alignment.CenterVertically) {
                Text(f.label, Modifier.weight(1f))
                Switch(checked = values[f.name] == true, onCheckedChange = { values[f.name] = it })
            }
            tip()
        }
        "choice" -> Column {
            if (f.label.isNotBlank()) Text(f.label, style = MaterialTheme.typography.labelLarge)
            f.choices.forEach { (value, words) ->
                Row(Modifier.fillMaxWidth().clickable { values[f.name] = value },
                    verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = values[f.name]?.toString() == value,
                        onClick = { values[f.name] = value })
                    Text(words)
                }
            }
            tip()
        }
        "checks" -> Column {
            if (f.label.isNotBlank()) Text(f.label, style = MaterialTheme.typography.labelLarge)
            val now = asList(values[f.name])
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                f.choices.forEach { (value, words) ->
                    FilterChip(selected = value in now, label = { Text(words) }, onClick = {
                        values[f.name] = if (value in now) now - value else now + value
                    })
                }
            }
            tip()
        }
        "file" -> Column {
            val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
                if (uri != null) model.uploadFor(uri) { token ->
                    values[f.name] = JSONObject().put("upload", token)
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = { pick.launch("image/*") }) { Text(f.label) }
                if (values[f.name] is JSONObject) Text("✓")
            }
            tip()
        }
        else -> Column {
            OutlinedTextField(value = values[f.name]?.toString() ?: "",
                onValueChange = { values[f.name] = it },
                label = if (f.label.isNotBlank()) { { Text(f.label) } } else null,
                singleLine = f.kind != "text", minLines = if (f.kind == "text") 3 else 1,
                modifier = Modifier.fillMaxWidth())
            tip()
        }
    }
}

private fun asList(v: Any?): List<String> = when (v) {
    is JSONArray -> (0 until v.length()).map { v.optString(it) }
    is List<*> -> v.map { it.toString() }
    else -> emptyList()
}

// ---- a profile ----------------------------------------------------------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProfilePlace(model: AppModel, p: Place.Profile, snack: SnackbarHostState, openBrowser: (String) -> Unit) {
    val view = model.profiles[p]
    val act = model.cardActions(openBrowser)
    val onLink: (String) -> Unit = { url -> model.openLink(url, openBrowser) }
    PlaceScaffold(view?.account?.name ?: "", model, snack) { mod ->
        if (view == null) {
            Box(mod, contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@PlaceScaffold
        }
        val a = view.account
        LazyColumn(mod, contentPadding = PaddingValues(bottom = 96.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                Column {
                    if (view.header.isNotBlank()) {
                        AsyncImage(model = view.header, contentDescription = null,
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.fillMaxWidth().height(120.dp))
                    }
                    Column(Modifier.padding(horizontal = 16.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Box(Modifier.offset(y = if (view.header.isNotBlank()) (-24).dp else 8.dp)) {
                            Face(a.avatar, a.name, a.handle, 72)
                        }
                        Text(a.name, style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold)
                        Text(view.meta.joinToString(" · ").ifBlank { "@" + a.handle },
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (view.counts.isNotBlank()) Text(view.counts, style = MaterialTheme.typography.bodySmall)
                        view.moved?.let { (words, who) ->
                            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                                .background(MaterialTheme.colorScheme.secondaryContainer).padding(8.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                Text("📦 $words", Modifier.weight(1f),
                                    style = MaterialTheme.typography.bodyMedium)
                                TextButton(onClick = { model.openProfile(who.id) }) {
                                    Text(view.movedOpen)
                                }
                            }
                        }
                        if (view.familiar.isNotBlank()) Text(view.familiar,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        view.featured.forEach { f -> Featured(model, f) }
                        if (view.note.isNotBlank()) HtmlText(view.note, onLink)
                        view.fields.forEach { (name, value, verified) ->
                            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                                .background(if (verified) MaterialTheme.colorScheme.secondaryContainer
                                            else MaterialTheme.colorScheme.surfaceVariant)
                                .padding(8.dp)) {
                                Text((if (verified) "✓ " else "") + name,
                                    style = MaterialTheme.typography.labelMedium)
                                HtmlText(value, onLink)
                            }
                        }
                        if (view.noteLine.isNotBlank()) Text(view.noteLine,
                            style = MaterialTheme.typography.bodySmall)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            view.actions.forEach { b ->
                                if (b.primary) Button(onClick = { model.profileAct(a.id, b.key) }) {
                                    Text(b.label)
                                } else OutlinedButton(onClick = { model.profileAct(a.id, b.key) }) {
                                    Text(b.label)
                                }
                            }
                        }
                        HorizontalDivider()
                        Row(Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            view.shows.forEach { (key, label, on) ->
                                FilterChip(selected = on, onClick = { model.openProfile(a.id, key) },
                                    label = { Text(label) })
                            }
                        }
                    }
                }
            }
            if (view.posts.isEmpty()) item {
                Text(stringResource(R.string.lane_empty), Modifier.fillMaxWidth().padding(24.dp),
                    textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            items(view.posts, key = { it.key }) { post ->
                Column(Modifier.padding(horizontal = 8.dp)) {
                    if (post.key in view.pinned) Text("📌 " + stringResource(R.string.pinned),
                        Modifier.padding(start = 8.dp, bottom = 2.dp),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    PostCard(post, act, model.hideSensitive)
                }
            }
            view.older?.let { offer ->
                item(key = "older") {
                    Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                        if (view.loadingMore) CircularProgressIndicator()
                        else OutlinedButton(onClick = { model.profileMore(p) }) { Text(offer.label) }
                    }
                }
            }
        }
    }
}

/** "Often writes about: #a, #b" — each tag its place; "Recommends: @x" — each a profile. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Featured(model: AppModel, f: FeaturedLine) {
    FlowRow(verticalArrangement = Arrangement.Center) {
        Text(f.title + " ", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
        f.tags.forEach { t ->
            Text("#$t ", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clickable { model.openPage("tag", t) })
        }
        f.people.forEach { a ->
            Text("@${a.handle} ", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clickable { model.openProfile(a.id) })
        }
    }
}
