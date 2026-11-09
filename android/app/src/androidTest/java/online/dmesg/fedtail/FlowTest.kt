package online.dmesg.fedtail

import android.content.Context
import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ComposeTimeoutException
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasScrollAction
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
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import androidx.compose.ui.test.swipeUp
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

    /** An item of the lane's ⋮ (09.11: refresh, find, mark all read live there). */
    private fun laneMenu(item: String) {
        compose.onAllNodesWithContentDescription("More: find", substring = true).onFirst()
            .performClick()
        waitText(item)
        compose.onAllNodesWithText(item).onFirst().performClick()
    }

    private fun waitDescription(text: String, ms: Long = 30_000, substring: Boolean = false) =
        waitFor("description \"$text\"", ms) {
            compose.onAllNodesWithContentDescription(text, substring = substring)
                .fetchSemanticsNodes().isNotEmpty()
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

    /** The overview of lanes is up: its title. ("Read in a row" was its mark until the
     *  button went, 112da6a8 — five tests waited 90 s for it in vain since.) */
    private fun overview() = waitText("Lanes", 90_000)

    @Test
    fun theOverviewOpensALaneAndAThread() {
        launch()
        overview()
        compose.onAllNodesWithText("Home").onFirst().performClick()
        waitDescription("open now", substring = true)                 // a lane's title bar
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
        // the card's own action, not a tap at its middle: that lands on a picture when
        // the first unread has one, and opens the viewer, not the thread
        compose.onAllNodes(card)[whole].performSemanticsAction(SemanticsActions.OnClick)
        waitText("/1")                                  // the thread, numbered as a tree
        waitText("Thread")
        back()
        waitDescription("open now", substring = true)                 // back in the lane…
        back()
        overview()                                      // …and back on the overview
    }

    @Test
    fun anAnswerFromElsewhereGrowsTheOpenThread() {
        // the open thread takes someone's answer in by itself, a round bringing it (the
        // bridge's "threads" count → AppModel.watch): tests/scenario.py's watch_thread
        launch("thread" to "101")
        waitText("/1")
        val words = "an answer from elsewhere " + System.currentTimeMillis()
        kotlinx.coroutines.runBlocking { Core.demoHappen("answer", "101", words) }
        waitText(words, 40_000)
    }

    @Test
    fun aReplyInAThreadStaysInSight() {
        launch("thread" to "101")
        waitText("/1")
        val words = "reply from the UI test " + System.currentTimeMillis()
        compose.onAllNodesWithContentDescription("Reply").onFirst().performClick()
        waitDescription("Send")
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextInput(words)
        compose.onAllNodesWithContentDescription("Send").onFirst().performClick()
        // back in the thread, standing on what was just written — not thrown to the top
        waitText(words, 30_000)
        waitText("Thread")
    }

    @Test
    fun theSwitcherFindsALaneByName() {
        launch("lane" to "home")
        waitDescription("open now", substring = true)  // the open lane's chip: its title
        compose.onAllNodesWithContentDescription("open now", substring = true).onFirst()
            .performClick()
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
        waitText("window.command_line", 15_000)         // the search left that one card
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
        assertTrue(file.readText().contains("[window]"))
    }

    @Test
    fun theTilesCanBeChanged() {
        launch()
        overview()
        compose.onAllNodesWithText("change").onFirst().performClick()
        waitText("✕")
        compose.onAllNodesWithText("✕").onFirst().performClick()  // the first tile goes
        waitText("PINNED")                              // a chosen order now (headings: caps)
        compose.onAllNodesWithText("done").onFirst().performClick()
        overview()
    }

    @Test
    fun theMenuOpensAPlaceOfTheWindows() {
        launch()
        overview()
        compose.onAllNodesWithContentDescription("More").onFirst().performClick()
        waitText("Places…", 15_000)
        compose.onAllNodesWithText("Places…").onFirst().performClick()
        waitText("Lists", 30_000)                      // common/places.py's ≡ menu
        compose.onAllNodesWithText("Search").onFirst().performClick()
        waitText("@user@server", 30_000)               // the search place's field
        back()
        waitText("Lists")
    }

    @Test
    fun aCardsMenuIsTheWindowsAndLeadsToTheProfile() {
        launch("thread" to "101")
        waitText("/1")
        compose.onAllNodesWithContentDescription("More").onFirst().performClick()
        compose.waitForIdle()  // the sheet slides up (09.11: a sheet, not a drop-down)
        waitText("Reply with quote", 60_000)           // common/actions.menu's items
        compose.onAllNodesWithText("Profile of @", substring = true).onFirst()
            .performScrollTo().performClick()
        waitText("Posts and replies", 30_000)          // a profile: what of theirs to show
    }

    @Test
    fun aLongPressOnACardOpensItsMenu() {
        launch()
        overview()
        compose.onAllNodesWithText("Home").onFirst().performClick()
        waitFor("a card", 90_000) { compose.onAllNodes(card).fetchSemanticsNodes().isNotEmpty() }
        // the card's long click (its label "More"), not a tap: the menu, not the thread
        val held = card and androidx.compose.ui.test.SemanticsMatcher.keyIsDefined(
            SemanticsActions.OnLongClick)
        compose.onAllNodes(held).onFirst().performSemanticsAction(SemanticsActions.OnLongClick)
        compose.waitForIdle()
        waitText("Reply with quote", 60_000)
        assert(compose.onAllNodesWithText("/1").fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun aRefreshKeepsThePlaceInTheLane() {
        launch("lane" to "home")
        waitDescription("open now", substring = true)
        waitFor("a card", 90_000) { compose.onAllNodes(card).fetchSemanticsNodes().isNotEmpty() }
        compose.waitForIdle()
        // what stands on screen now, and where: after ⟳ the same card, the same place
        val before = compose.onAllNodes(card).fetchSemanticsNodes()
            .map { it.boundsInRoot.top to it.config.getOrNull(SemanticsProperties.Text)?.joinToString() }
        laneMenu("Refresh")
        Thread.sleep(4_000)  // a round (the demo's server answers at once) and its reload
        compose.waitForIdle()
        val after = compose.onAllNodes(card).fetchSemanticsNodes()
            .map { it.boundsInRoot.top to it.config.getOrNull(SemanticsProperties.Text)?.joinToString() }
        val first = before.first()
        val same = after.firstOrNull { it.second == first.second }
        assertTrue("the card read before is gone: $before → $after", same != null)
        assertTrue("the lane jumped: ${first.first} → ${same!!.first}",
            kotlin.math.abs(same.first - first.first) < 2f)
    }

    @Test
    fun theArrowStaysAfterMarkAllRead() {
        // "Mark all read" left no arrow: the newest end was a long scroll away (02.11)
        launch("lane" to "home")
        waitDescription("open now", substring = true)
        waitFor("a card", 90_000) { compose.onAllNodes(card).fetchSemanticsNodes().isNotEmpty() }
        // "Mark all read" is in the lane's ⋮ now (09.11), undone within 5 s
        compose.onAllNodesWithContentDescription("More: find", substring = true).onFirst()
            .performClick()
        val all = compose.onAllNodesWithText("Mark all read")
        if (all.fetchSemanticsNodes().isNotEmpty()) all.onFirst().performClick()
        else compose.onAllNodesWithText("Find").onFirst().performClick()  // (menu closed)
        // the arrow shows where it leads somewhere (09.11): away from the newest end
        val newestUp = compose.onAllNodesWithContentDescription("Nothing new: to the newest")
        repeat(8) {
            if (newestUp.fetchSemanticsNodes().isNotEmpty()) return@repeat
            compose.onAllNodes(card).onFirst().performTouchInput { swipeDown() }
            compose.waitForIdle()
        }
        waitDescription("Nothing new: to the newest")
        compose.onAllNodesWithContentDescription("Nothing new: to the newest").onFirst().performClick()
        waitDescription("open now", substring = true)
    }

    @Test
    fun myProfileIsInTheMenu() {
        // the windows' "My profile": the phone had no way there but my own post (02.11)
        launch()
        overview()
        compose.onAllNodesWithContentDescription("More").onFirst().performClick()
        waitText("My profile", 15_000)
        compose.onAllNodesWithText("My profile").onFirst().performClick()
        waitText("Posts and replies", 30_000)          // a profile: what of theirs to show
    }

    @Test
    fun theInterfaceLanguageIsTheAppsToo() {
        // ui.language = "ru" on a phone in English: the core's words went Russian, the
        // app's own (its buttons, its menus) stayed English. Android 13+ only: before it
        // an app has no language of its own (the app says it follows a restart)
        org.junit.Assume.assumeTrue(android.os.Build.VERSION.SDK_INT >= 33)
        launch("lane" to "home")
        waitDescription("open now", substring = true)
        try {
            kotlinx.coroutines.runBlocking {
                Core.settingSet("ui", "language", "\"ru\"")
                Core.settingsApply()
            }
            scenario?.close()
            launch("lane" to "home")
            waitDescription("открыта сейчас", 60_000, substring = true)  // the lane's chip
        } finally {
            kotlinx.coroutines.runBlocking {
                Core.settingSet("ui", "language", "null")
                Core.settingsApply()
            }
            val context = ApplicationProvider.getApplicationContext<Context>()
            context.getSystemService(android.app.LocaleManager::class.java).applicationLocales =
                android.os.LocaleList.getEmptyLocaleList()
        }
    }

    @Test
    fun aRefusedTokenSaysSoAndLeadsToLoggingInAgain() {
        // the server revoked the token: the phone said nothing and every answer was 401
        launch("lane" to "home")
        waitDescription("open now", substring = true)
        kotlinx.coroutines.runBlocking { Core.demoHappen("token_refused", "", "") }
        waitText("The token is no longer accepted", 40_000)
        compose.onAllNodesWithText("Log in again…").onFirst().performClick()
        waitText("Account and server", 30_000)  // Accounts: "Log in again…" is there
    }

    @Test
    fun anAnsweredRequestKeepsThePlace() {
        // a follow request answered: the lane jumped to its start (02.11)
        launch("lane" to "activity")
        waitDescription("open now", substring = true)
        kotlinx.coroutines.runBlocking { Core.demoHappen("requests", "req", "20") }
        // the requests stand where they come in time: past the demo's posts of 2099, maybe
        // a long way down — swiped to (the lane jumping would take them off the screen)
        fun shownRequests() = compose.onAllNodes(hasText("@example.org", substring = true))
            .fetchSemanticsNodes().count { it.boundsInRoot.top > 0f }
        Thread.sleep(3_000)  // the round bringing them; new ones wait for ⟳ (reading.on_new)
        laneMenu("Refresh")
        Thread.sleep(3_000)
        // wherever they stand: down the lane first, then up (the order is the config's)
        for (up in listOf(true, false)) repeat(30) {
            if (shownRequests() >= 3) return@repeat
            compose.onAllNodes(hasScrollAction()).onFirst()
                .performTouchInput { if (up) swipeUp() else swipeDown() }
            compose.waitForIdle()
            Thread.sleep(300)
        }
        waitFor("the requests", 20_000) { shownRequests() >= 3 }
        Thread.sleep(1_000)
        fun names() = compose.onAllNodes(hasText("@example.org", substring = true))
            .fetchSemanticsNodes()
            .map { it.boundsInRoot.top to it.config.getOrNull(SemanticsProperties.Text)!!.joinToString() }
            .filter { it.first > 0f }.sortedBy { it.first }
        val before = names()
        val (at, answered) = before[0]  // the topmost request on screen
        val (was, under) = before[1]    // the row under it
        val buttons = compose.onAllNodesWithText("✔ approve")
        val shown = buttons.fetchSemanticsNodes()
        val i = shown.indices.filter { shown[it].boundsInRoot.top > at }
            .minBy { shown[it].boundsInRoot.top }  // its yes
        buttons[i].performClick()
        waitFor("$answered gone", 30_000) { names().none { it.second == answered } }
        Thread.sleep(2_000)
        compose.waitForIdle()
        val now = names().firstOrNull { it.second == under }
        assertTrue("$under left the screen: $before → ${names()}", now != null)
        // it stays, or takes the answered row's place: no more than a row's way
        assertTrue("the lane jumped: $under $was → ${now!!.first}",
            kotlin.math.abs(now.first - was) <= was - at + 4f)
    }
}
