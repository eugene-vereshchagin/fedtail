package online.dmesg.fedtail

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import org.json.JSONObject

/**
 * Step one of the port: start the core inside the app and show what it says about itself.
 * Proves the whole chain — Kotlin → Chaquopy → fedtail's core → SQLite, TLS — on a phone.
 * The lanes, threads and the rest come next, over the same Core.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { FedtailTheme { StartScreen() } }
    }
}

@Composable
fun FedtailTheme(content: @Composable () -> Unit) {
    val context = LocalContext.current
    val colors = if (isSystemInDarkTheme()) dynamicDarkColorScheme(context)
    else dynamicLightColorScheme(context)
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable
fun StartScreen() {
    val context = LocalContext.current
    var info by remember { mutableStateOf<JSONObject?>(null) }
    var failure by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        try {
            info = Core.start(context)
        } catch (e: Exception) { // a Python error comes as PyException: show it, don't crash
            failure = e.toString()
        }
    }
    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            val got = info
            when {
                failure != null -> Problem(failure!!)
                got == null -> Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    CircularProgressIndicator()
                    Text(stringResource(R.string.starting))
                }
                got.has("error") -> Problem(got.optString("error") + "\n\n" + got.optString("trace"))
                else -> Facts(got)
            }
        }
    }
}

@Composable
private fun Facts(info: JSONObject) {
    Text(stringResource(R.string.core_ok), style = MaterialTheme.typography.headlineSmall)
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Fact(stringResource(R.string.label_version), info.optString("version"))
            Fact(stringResource(R.string.label_python),
                info.optString("python") + " · " + info.optString("abi"))
            Fact(stringResource(R.string.label_ssl), info.optString("ssl"))
            Fact(stringResource(R.string.label_store), info.optJSONObject("store")?.let {
                "${it.optDouble("db_mb")} MB · ${it.optInt("statuses")} posts"
            } ?: "")
            val profiles = info.optJSONArray("profiles")
            Fact(stringResource(R.string.label_profiles),
                if (profiles == null || profiles.length() == 0) stringResource(R.string.none)
                else (0 until profiles.length()).joinToString { profiles.getString(it) })
            Fact(stringResource(R.string.label_sync),
                stringResource(if (info.optBoolean("sync")) R.string.yes else R.string.no))
            if (info.has("started_ms")) {
                Fact(stringResource(R.string.label_started), "${info.optInt("started_ms")} ms")
            }
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

@Composable
private fun Problem(text: String) {
    Text(stringResource(R.string.core_failed), style = MaterialTheme.typography.headlineSmall,
        color = MaterialTheme.colorScheme.error)
    Card(modifier = Modifier.fillMaxWidth()) {
        Text(text, modifier = Modifier.padding(16.dp), fontFamily = FontFamily.Monospace,
            style = MaterialTheme.typography.bodySmall)
    }
}
