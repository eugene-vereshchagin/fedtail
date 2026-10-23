package online.dmesg.fedtail

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
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
 * The settings page (the phone only; the desktop keeps the file): every option of the
 * config file, by the example's chapters, with its explanation and a control by its
 * kind — a switch, the choices, a number, words, a list. Each change is written into
 * the file at once (checked first), and takes effect when the page is left. "As a file"
 * opens the file itself.
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
                        it.help.contains(q, true) || c.title.contains(q, true)
                })
            }.filter { it.options.isNotEmpty() }
            LazyColumn(contentPadding = PaddingValues(bottom = 48.dp)) {
                shown.forEach { c ->
                    item(key = "c-" + c.title) {
                        SmallHead(c.title, Modifier.padding(start = 16.dp, end = 16.dp,
                            top = 20.dp, bottom = 4.dp))
                    }
                    items(c.options, key = { it.section + "." + it.key }) { opt ->
                        OptionRow(opt) { json -> model.setSetting(opt, json) }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun OptionRow(opt: Setting, set: (String) -> Unit) {
    var more by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("${opt.section}.${opt.key}", fontFamily = FontFamily.Monospace, fontSize = 14.sp,
                fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            if (opt.type == "bool") {
                Switch(checked = opt.value == "true",
                    onCheckedChange = { set(if (it) "true" else "false") })
            }
        }
        if (opt.help.isNotBlank()) {
            Text(opt.help, fontSize = 13.sp, lineHeight = 18.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = if (more) Int.MAX_VALUE else 3, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.clickable { more = !more })
        }
        when {
            opt.type == "bool" -> {}
            opt.choices != null -> FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                opt.choices.forEach { c ->
                    FilterChip(selected = opt.value == JSONObject.quote(c),
                        onClick = { set(JSONObject.quote(c)) }, label = { Text(c) })
                }
            }
            else -> Typed(opt, set)
        }
        if (opt.value != opt.dflt) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.default_is, shown(opt.dflt)), fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                TextButton(onClick = { set(opt.dflt) }) { Text(stringResource(R.string.reset)) }
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
    val numeric = opt.type == "int" || opt.type == "float"
    val write = {
        val json = when (opt.type) {
            "int" -> text.trim().toLongOrNull()?.toString()
            "float" -> text.trim().replace(',', '.').toDoubleOrNull()?.toString()
            "list" -> JSONArray(text.split(',').map { it.trim() }.filter { it.isNotEmpty() }).toString()
            else -> JSONObject.quote(text)
        }
        if (json != null) set(json)
    }
    OutlinedTextField(text, { text = it }, singleLine = true,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (numeric) KeyboardType.Number else KeyboardType.Text,
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
        json.startsWith("[") -> JSONArray(json).let { a -> (0 until a.length()).joinToString(", ") { a.get(it).toString() } }
        else -> json
    }
} catch (e: Exception) {
    json
}
