package online.dmesg.fedtail

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.Velocity
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

/**
 * Pull to refresh from the bottom: a lane read "as a forum" (oldest first, feed.order) has
 * its newest posts at the end, so that is where one asks for more — dragged further up
 * than the list goes, and let go past the mark. Nothing moves in the list itself: what
 * comes lands under what is read, and the place stays where it is.
 */
@Composable
fun BottomPullToRefresh(
    refreshing: Boolean, onRefresh: () -> Unit, modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val far = with(LocalDensity.current) { 96.dp.toPx() }
    var pulled by remember { mutableFloatStateOf(0f) }
    val refresh by rememberUpdatedState(onRefresh)
    val conn = remember(far) {
        object : NestedScrollConnection {
            override fun onPreScroll(available: Offset, source: NestedScrollSource): Offset {
                // the finger going back down: first the pull gives way, then the list
                if (pulled > 0f && available.y > 0f) {
                    val take = minOf(pulled, available.y * 0.5f)
                    pulled -= take
                    return Offset(0f, available.y)
                }
                return Offset.Zero
            }

            override fun onPostScroll(consumed: Offset, available: Offset,
                                      source: NestedScrollSource): Offset {
                // at the end and still dragged up: that's the pull (half as far: it resists)
                if (source == NestedScrollSource.UserInput && available.y < 0f) {
                    pulled = minOf(pulled - available.y * 0.5f, far * 1.5f)
                    return Offset(0f, available.y)
                }
                return Offset.Zero
            }

            override suspend fun onPreFling(available: Velocity): Velocity {
                val had = pulled
                pulled = 0f
                if (had >= far) refresh()
                return if (had > 0f) available else Velocity.Zero
            }
        }
    }
    Box(modifier.nestedScroll(conn)) {
        content()
        if (refreshing || pulled > 0f) {
            val lift = if (refreshing) far * 0.6f else minOf(pulled, far)
            Surface(shape = CircleShape, shadowElevation = 3.dp,
                color = MaterialTheme.colorScheme.surface,
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 8.dp)
                    .offset { IntOffset(0, -lift.roundToInt()) }.size(40.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    if (refreshing) CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.5.dp)
                    else CircularProgressIndicator(progress = { (pulled / far).coerceIn(0f, 1f) },
                        modifier = Modifier.size(24.dp), strokeWidth = 2.5.dp)
                }
            }
        }
    }
}
