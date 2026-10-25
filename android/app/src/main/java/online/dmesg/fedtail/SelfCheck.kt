package online.dmesg.fedtail

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject

/**
 * The self-check (dev builds, ⋮ → Self-check): the core, the server, every lane, a thread,
 * pictures, a link, the settings, sync — on this phone with this account, read-only
 * (nothing is posted, liked or marked read). Each step says ok or what broke and how long
 * it took; "Share the report" hands over the desktop's bug report with the steps in it
 * (the logs, the config, the system — never the token or the database).
 */
@Composable
fun SelfCheckPlace(model: AppModel, snack: SnackbarHostState, share: (String) -> Unit) {
    val context = LocalContext.current
    PlaceScaffold(stringResource(R.string.selfcheck), model, snack) { mod ->
        Column(mod.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.selfcheck_intro), fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Button(onClick = { model.runSelfCheck() }, enabled = !model.checking) {
                    Text(stringResource(R.string.selfcheck_run))
                }
                if (model.checks.isNotEmpty() && !model.checking) {
                    OutlinedButton(onClick = { model.selfCheckReport(deviceFacts(context), share) }) {
                        Text(stringResource(R.string.selfcheck_share))
                    }
                }
                if (model.checking) CircularProgressIndicator(Modifier.width(24.dp))
            }
            val bad = model.checks.count { it.ok == false }
            if (model.checks.isNotEmpty() && !model.checking) {
                Text(if (bad == 0) stringResource(R.string.selfcheck_all_ok)
                     else stringResource(R.string.selfcheck_bad, bad),
                    fontWeight = FontWeight.SemiBold,
                    color = if (bad == 0) MaterialTheme.colorScheme.tertiary
                            else MaterialTheme.colorScheme.error)
            }
            LazyColumn {
                items(model.checks, key = { it.name }) { c ->
                    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(when (c.ok) {
                                null -> "…"
                                true -> "✓"
                                false -> "✗"
                            }, fontSize = 18.sp, modifier = Modifier.width(28.dp),
                                color = when (c.ok) {
                                    true -> MaterialTheme.colorScheme.tertiary
                                    false -> MaterialTheme.colorScheme.error
                                    null -> MaterialTheme.colorScheme.onSurfaceVariant
                                })
                            Text(c.name, fontFamily = FontFamily.Monospace, fontSize = 15.sp,
                                modifier = Modifier.weight(1f))
                            if (c.ok != null) {
                                Text("${c.ms} ms", fontSize = 13.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        if (c.detail.isNotBlank()) {
                            Text(c.detail, fontSize = 12.sp, lineHeight = 16.sp,
                                modifier = Modifier.padding(start = 28.dp),
                                color = if (c.ok == false) MaterialTheme.colorScheme.error
                                        else MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                }
            }
        }
    }
}

/** What the report says about the phone itself. */
fun deviceFacts(context: Context): JSONObject {
    val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
    val mem = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
    val dm = context.resources.displayMetrics
    return JSONObject()
        .put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
        .put("android", "${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
        .put("abi", Build.SUPPORTED_ABIS.joinToString(", "))
        .put("memory", "${mem.totalMem / 1048576} MB, free ${mem.availMem / 1048576} MB, " +
            "app limit ${am.memoryClass} MB")
        .put("screen", "${(dm.widthPixels / dm.density).toInt()}×${(dm.heightPixels / dm.density).toInt()} dp, " +
            "density ${dm.density}")
        .put("app", "${BuildConfig.APPLICATION_ID} ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
        // what decides whether notifications come: allowed, a push distributor, whether
        // the system may put the app to sleep (the 15-minute rounds then come late)
        .put("notifications", if (androidx.core.app.NotificationManagerCompat.from(context)
            .areNotificationsEnabled()) "allowed" else "OFF")
        .put("push", runCatching {
            org.unifiedpush.android.connector.UnifiedPush.getAckDistributor(context)
                ?: ("none (" + org.unifiedpush.android.connector.UnifiedPush
                    .getDistributors(context).size + " installed)")
        }.getOrElse { "? ${it.javaClass.simpleName}" })
        .put("battery", runCatching {
            val pm = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
            if (pm.isIgnoringBatteryOptimizations(context.packageName)) "unrestricted"
            else "optimized (background rounds may come late)"
        }.getOrElse { "?" })
}
