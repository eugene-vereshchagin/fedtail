package online.dmesg.fedtail

import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.TextToolbar
import androidx.compose.ui.platform.TextToolbarStatus

/** A post's words selected (phone.hold_text = "select"). Compose keeps a selection to
 *  itself, so the "Copy" bar over it tells: shown — something is selected, hidden — not.
 *  While it is, the first tap anywhere and Back only take the selection away: a tap
 *  beside it opened the post, Back went back in the lane, and nothing let go of it
 *  (12.11). Clearing: every post's SelectionContainer is keyed by [epoch]. */
object TextSelection {
    var active by mutableStateOf(false)
        private set
    var epoch by mutableIntStateOf(0)
        private set
    private var bar: TextToolbar? = null

    fun clear() {
        bar?.hide()
        active = false
        epoch++
    }

    internal fun shown(by: TextToolbar) {
        bar = by
        active = true
    }

    internal fun hidden() {
        active = false
    }

    /** The words' card gone (scrolled away, the screen closed, the app left): its
     *  selection with it — never a stale one eating the next tap. */
    internal fun gone(by: TextToolbar) {
        if (bar === by) {
            bar = null
            active = false
        }
    }
}

/** The platform's "Copy" bar, telling [TextSelection] when it shows and hides; only
 *  around a post's words (the editor's fields keep the plain one). */
class TrackingToolbar(private val inner: TextToolbar) : TextToolbar {
    override val status: TextToolbarStatus get() = inner.status

    override fun hide() {
        inner.hide()
        TextSelection.hidden()
    }

    override fun showMenu(
        rect: Rect,
        onCopyRequested: (() -> Unit)?,
        onPasteRequested: (() -> Unit)?,
        onCutRequested: (() -> Unit)?,
        onSelectAllRequested: (() -> Unit)?,
    ) {
        inner.showMenu(rect, onCopyRequested, onPasteRequested, onCutRequested, onSelectAllRequested)
        TextSelection.shown(this)
    }
}

/** Over the whole screen: while a post's words are selected, the first touch anywhere
 *  only lets go of them — taken before the cards and buttons under it see it (the
 *  selection's handles and its "Copy" bar are windows of their own: untouched). */
fun Modifier.letGoOfSelection(): Modifier = pointerInput(Unit) {
    awaitEachGesture {
        val down = awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
        if (!TextSelection.active) return@awaitEachGesture
        down.consume()
        TextSelection.clear()
        // the rest of this touch too: a lift must not become a tap below
        while (true) {
            val ev = awaitPointerEvent(PointerEventPass.Initial)
            ev.changes.forEach { it.consume() }
            if (ev.changes.all { !it.pressed }) break
        }
    }
}
