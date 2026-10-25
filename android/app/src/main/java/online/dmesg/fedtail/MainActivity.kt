package online.dmesg.fedtail

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.core.content.FileProvider
import java.io.File

/**
 * The one window: the overview of lanes, a lane, and what opens over it (Screens.kt).
 */
class MainActivity : ComponentActivity() {
    private val model: AppModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // demo: the made-up world of fedtail's screenshots (CI's emulator), dev builds only
        val demo = BuildConfig.DEBUG && intent.getBooleanExtra("demo", false)
        // a note tapped in the shade: its thread or lane (any build); the demo's own extras
        val noteThread = intent.getStringExtra(Notifier.EXTRA_THREAD)?.takeIf { it.isNotBlank() }
        val noteLane = intent.getStringExtra(Notifier.EXTRA_LANE)?.takeIf { it.isNotBlank() }
        model.start(demo,
            openThread = noteThread ?: if (demo) intent.getStringExtra("thread") else null,
            openLane = noteLane ?: if (demo) intent.getStringExtra("lane") else null,
            openSettings = demo && intent.getBooleanExtra("settings", false),
            openPage = if (demo) intent.getStringExtra("page") else null,
            openProfile = if (demo) intent.getStringExtra("profile") else null,
            openCompose = demo && intent.getBooleanExtra("compose", false))
        handleLogin(intent)
        if (!demo) askToNotify()  // the demo (CI's emulator): no system dialog over the screens
        setContent {
            FedtailTheme(model.themeColors, model.themeLight, model.themeFont, model.themeScale,
                model.themePictures) {
                App(model, openBrowser = { url ->
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                }, share = { path -> shareFile(path) })
            }
        }
    }

    /** The self-check's report to a messenger, mail or files: the system's share sheet. */
    private fun shareFile(path: String) {
        val uri = FileProvider.getUriForFile(this, "${BuildConfig.APPLICATION_ID}.files", File(path))
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "application/gzip"
            putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_SUBJECT, File(path).name)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(send, null))
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleLogin(intent)
        val thread = intent.getStringExtra(Notifier.EXTRA_THREAD)
        val lane = intent.getStringExtra(Notifier.EXTRA_LANE)
        if (thread != null || lane != null) model.openFromNote(lane, thread)
    }

    private val notifyAsk = registerForActivityResult(
        ActivityResultContracts.RequestPermission()) { /* the shade works from now, or not */ }

    /** The shade needs a yes (Android 13+): asked once; "no" stays no until the settings. */
    private fun askToNotify() {
        if (Notifier.allowed(this)) return
        val prefs = getSharedPreferences("app", MODE_PRIVATE)
        if (prefs.getBoolean("asked_notify", false)) return
        prefs.edit().putBoolean("asked_notify", true).apply()
        notifyAsk.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    /** fedtail://oauth?code=… — the server sends the browser back here after "allow". */
    private fun handleLogin(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme != "fedtail" || data.host != "oauth") return
        val code = data.getQueryParameter("code")
        if (code != null) model.finishLogin(code)
        else data.getQueryParameter("error_description")?.let { model.message = it }
    }

    override fun onStart() {
        super.onStart()
        Notifier.visible = true
        model.onForeground()
    }

    override fun onStop() {
        Notifier.visible = false
        model.onBackground()
        super.onStop()
    }
}
