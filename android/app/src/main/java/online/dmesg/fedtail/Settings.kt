package online.dmesg.fedtail

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONArray
import org.json.JSONObject

/**
 * The settings page — the desktop's settings window on a phone (common/settings.py gives
 * both the same chapters, names, explanations and choices; only what the phone heeds is
 * here). A change goes into config.toml at once, that one line (core/config_edit.py), and
 * takes effect when the page is left. "As a file" opens the file itself.
 */
@Composable
fun SettingsPlace(model: AppModel, snack: SnackbarHostState) {
    var find by rememberSaveable { mutableStateOf(model.settingsQuery) }
    PlaceScaffold(stringResource(R.string.settings), model, snack, actions = {
        TextButton(onClick = { model.openConfig() }) { Text(stringResource(R.string.as_file)) }
    }) { mod ->
        Column(mod.imePadding()) {
            OutlinedTextField(find, { find = it }, singleLine = true,
                leadingIcon = { Icon(Icons.Filled.Search, null) },
                placeholder = { Text(stringResource(R.string.find_setting)) },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp))
            val q = find.trim()
            val shown = model.settings.map { c ->
                c.copy(options = c.options.filter {
                    q.isEmpty() || "${it.section}.${it.key}".contains(q, true) ||
                        it.title.contains(q, true) || it.about.contains(q, true) ||
                        c.title.contains(q, true)
                })
            }.filter { it.options.isNotEmpty() }
            LazyColumn(contentPadding = PaddingValues(bottom = 48.dp)) {
                shown.forEach { c ->
                    item(key = "c-" + c.title) {
                        SmallHead(c.title, Modifier.padding(start = 16.dp, end = 16.dp,
                            top = 20.dp, bottom = 4.dp))
                    }
                    items(c.options, key = { it.section + "." + it.key }) { opt ->
                        OptionCard(opt) { json -> model.setSetting(opt, json) }
                    }
                }
            }
        }
    }
}

/** One option as the desktop's card: its name, the explanation, the control, "Default". */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun OptionCard(opt: Setting, set: (String) -> Unit) {
    var more by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(opt.title, fontSize = 16.sp, fontWeight = FontWeight.Medium)
                Text("${opt.section}.${opt.key}", fontFamily = FontFamily.Monospace,
                    fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (opt.kind == "bool") {
                Switch(checked = opt.value == "true",
                    onCheckedChange = { set(if (it) "true" else "false") })
            }
        }
        if (opt.about.isNotBlank()) {
            Text(opt.about, fontSize = 13.sp, lineHeight = 18.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = if (more) Int.MAX_VALUE else 3, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.clickable { more = !more })
        }
        when (opt.kind) {
            "bool" -> {}
            // a choice with what each one means, as the desktop's card shows it
            "choice" -> Column {
                opt.choices.forEach { (value, words) ->
                    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).clickable { set(value) },
                        verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = opt.value == value, onClick = { set(value) })
                        Column(Modifier.weight(1f)) {
                            Text(shown(value), fontFamily = FontFamily.Monospace, fontSize = 14.sp)
                            if (words.isNotBlank() && words != shown(value)) {
                                Text(words, fontSize = 13.sp, maxLines = 2,
                                    overflow = TextOverflow.Ellipsis,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
            // ticks: lanes, kinds of activity…
            "checks" -> FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                val on = listOf(opt.value)
                    .flatMap { v -> runCatching { JSONArray(v) }.getOrNull()?.let { a ->
                        (0 until a.length()).map { JSONObject.quote(a.getString(it)) } } ?: emptyList() }
                opt.choices.forEach { (value, words) ->
                    FilterChip(selected = value in on, label = { Text(words.ifBlank { shown(value) }) },
                        onClick = {
                            val next = if (value in on) on - value else on + value
                            set(JSONArray(next.map { shown(it) }).toString())
                        })
                }
            }
            else -> Typed(opt, set)
        }
        if (opt.changed) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.default_is, shown(opt.dflt)), fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                TextButton(onClick = { set("null") }) { Text(stringResource(R.string.reset)) }
            }
        }
    }
    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
}

/** A number, words or a list (comma-separated): typed, then ✓ (or Enter) writes it. */
@Composable
private fun Typed(opt: Setting, set: (String) -> Unit) {
    val now = shown(opt.value)
    var text by remember(opt.value) { mutableStateOf(now) }
    val write = {
        val json = when (opt.kind) {
            "int" -> text.trim().toLongOrNull()?.toString()
            "list" -> JSONArray(text.split(',').map { it.trim().trim('"') }.filter { it.isNotEmpty() }).toString()
            else -> JSONObject.quote(text)
        }
        if (json != null) set(json)
    }
    OutlinedTextField(text, { text = it }, singleLine = true,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (opt.kind == "int") KeyboardType.Number else KeyboardType.Text,
            imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { if (text != now) write() }),
        trailingIcon = {
            if (text != now) IconButton(onClick = { write() }) {
                Icon(Icons.Filled.Check, stringResource(R.string.save))
            }
        },
        textStyle = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
        modifier = Modifier.fillMaxWidth())
}

/** A value as a person reads it: words without quotes, a list as "a, b". */
private fun shown(json: String): String = try {
    when {
        json.startsWith("\"") -> JSONArray("[$json]").getString(0)
        json.startsWith("[") -> JSONArray(json).let { a ->
            (0 until a.length()).joinToString(", ") { a.get(it).toString() }
        }
        else -> json
    }
} catch (e: Exception) {
    json
}
