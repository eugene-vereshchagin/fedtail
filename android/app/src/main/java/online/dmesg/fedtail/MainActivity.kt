package online.dmesg.fedtail

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels

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
        model.start(demo, openThread = if (demo) intent.getStringExtra("thread") else null,
            openLane = if (demo) intent.getStringExtra("lane") else null)
        handleLogin(intent)
        setContent {
            FedtailTheme {
                App(model, openBrowser = { url ->
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                })
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleLogin(intent)
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
        model.onForeground()
    }

    override fun onStop() {
        model.onBackground()
        super.onStop()
    }
}
