package online.dmesg.fedtail

import android.content.Context
import android.content.Intent
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ComposeTimeoutException
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isOff
import androidx.compose.ui.test.isOn
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.isToggleable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The app's ways on the emulator, in the demo world (tools/showcase.py: Мира, Кот, the
 * router thread): tap and check what came of it — where CI's screenshots only look.
 * The emulator speaks English; the made-up posts are Russian.
 */
@RunWith(AndroidJUnit4::class)
class FlowTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(vararg extras: Pair<String, Any>) {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val intent = Intent(context, MainActivity::class.java).putExtra("demo", true)
        extras.forEach { (k, v) ->
            when (v) {
                is String -> intent.putExtra(k, v)
                is Boolean -> intent.putExtra(k, v)
            }
        }
        scenario = ActivityScenario.launch(intent)
    }

    @After
    fun close() {
        scenario?.close()
    }

    /** Python starts slowly on an emulator: the first screen gets a minute and a half. */
    private fun waitText(text: String, ms: Long = 90_000) = waitFor("text \"$text\"", ms) {
        compose.onAllNodesWithText(text, substring = true).fetchSemanticsNodes().isNotEmpty()
    }

    private fun waitDescription(text: String, ms: Long = 30_000) =
        waitFor("description \"$text\"", ms) {
            compose.onAllNodesWithContentDescription(text).fetchSemanticsNodes().isNotEmpty()
        }

    /** Waits; on a timeout says what it waited for and what the screen held instead. */
    private fun waitFor(what: String, ms: Long, ok: () -> Boolean) {
        try {
            compose.waitUntil(ms) { ok() }
        } catch (e: ComposeTimeoutException) {
            val screen = try {
                compose.onAllNodes(isRoot()).fetchSemanticsNodes().joinToString("\n---\n") {
                    it.printTree()
                }
            } catch (x: Throwable) {
                "(no screen: $x)"
            }
            throw AssertionError("waited ${ms / 1000} s for $what; the screen:\n$screen", e)
        }
    }

    private fun SemanticsNode.printTree(depth: Int = 0): String {
        val words = (config.getOrNull(SemanticsProperties.Text)?.joinToString(" ") ?: "") +
            (config.getOrNull(SemanticsProperties.ContentDescription)
                ?.joinToString(" ", prefix = " [", postfix = "]") ?: "")
        val me = if (words.isBlank()) "" else "  ".repeat(depth) + words.trim() + "\n"
        return me + children.joinToString("") { it.printTree(depth + 1) }
    }

    /** A post's card: clickable, with an author's @handle in its words. */
    private val card = hasClickAction() and hasText("@", substring = true)

    private fun back() = scenario!!.onActivity { it.onBackPressedDispatcher.onBackPressed() }

    @Test
    fun theOverviewOpensALaneAndAThread() {
        launch()
        waitText("Read in a row")
        compose.onAllNodesWithText("Home").onFirst().performClick()
        waitDescription("Switch lane")                 // a lane's title bar
        // a card — whichever stands first: the screenshots before have read some already,
        // and a lane opens on its first unread post
        waitFor("a card", 90_000) {
            compose.onAllNodes(card).fetchSemanticsNodes().isNotEmpty()
        }
        // one standing whole on screen: the first may sit half under the title bar, and a
        // tap at its middle would land on the bar
        val nodes = compose.onAllNodes(card).fetchSemanticsNodes()
        val bottom = compose.onAllNodes(isRoot()).fetchSemanticsNodes().maxOf { it.boundsInRoot.bottom }
        val whole = nodes.indices.firstOrNull { i ->
            nodes[i].boundsInRoot.top > 250f && nodes[i].boundsInRoot.bottom < bottom
        } ?: nodes.indices.maxBy { nodes[it].boundsInRoot.top }
        compose.onAllNodes(card)[whole].performClick()
        waitText("/1")                                  // the thread, numbered as a tree
        waitText("Thread")
        back()
        waitDescription("Switch lane")                 // back in the lane…
        back()
        waitText("Read in a row")                       // …and back on the overview
    }

    @Test
    fun readInARowLeavesTheOverviewForALaneWithNews() {
        launch()
        waitText("Read in a row")
        compose.onAllNodesWithText("Read in a row").onFirst().performClick()
        waitDescription("Switch lane")
    }

    @Test
    fun theSwitcherFindsALaneByName() {
        launch("lane" to "home")
        waitDescription("Switch lane")
        compose.onAllNodesWithContentDescription("Switch lane").onFirst().performClick()
        waitText("lane, list or #tag")                  // the switcher's search
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextInput("Fed")
        waitText("Federated")
        compose.onAllNodesWithText("Federated").onFirst().performClick()
        waitText("Federated")
    }

    @Test
    fun aSettingGoesIntoTheConfigFile() {
        launch("settings" to true)
        waitText("Settings")
        waitText("Find a setting", 30_000)
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextInput("command_line")
        waitText("ui.command_line", 15_000)             // the search left that one card
        val file = File(ApplicationProvider.getApplicationContext<Context>().filesDir,
            "config/fedtail/demo/config.toml")
        val before = file.readText().contains("command_line = true")
        compose.onAllNodes(isToggleable()).onFirst().performClick()
        compose.waitUntil(15_000) { file.readText().contains("command_line = true") != before }
        // the switch shows what the file says now — only then back as it was
        val shown = if (before) isOff() else isOn()
        compose.waitUntil(15_000) {
            compose.onAllNodes(isToggleable() and shown).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onAllNodes(isToggleable()).onFirst().performClick()
        compose.waitUntil(15_000) { file.readText().contains("command_line = true") == before }
        assertTrue(file.readText().contains("[ui]"))
    }

    @Test
    fun theTilesCanBeChanged() {
        launch()
        waitText("Read in a row")
        compose.onAllNodesWithText("change").onFirst().performClick()
        waitText("✕")
        compose.onAllNodesWithText("✕").onFirst().performClick()  // the first tile goes
        waitText("PINNED")                              // a chosen order now (headings: caps)
        compose.onAllNodesWithText("done").onFirst().performClick()
        waitText("Read in a row")
    }
}
