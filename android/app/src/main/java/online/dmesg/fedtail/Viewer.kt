package online.dmesg.fedtail

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest

/**
 * A post's pictures over everything: black, one at a time (‹ › between them), pinch to
 * zoom, a double tap back to whole; the description (alt) below. A video or sound opens
 * in the browser (or the player the phone offers) — no player of our own yet.
 */
@Composable
fun MediaViewer(place: Place.Media, close: () -> Unit, openBrowser: (String) -> Unit) {
    var index by remember(place) { mutableIntStateOf(place.index.coerceIn(0, place.items.size - 1)) }
    val m = place.items[index]
    var scale by remember(index) { mutableFloatStateOf(1f) }
    var offset by remember(index) { mutableStateOf(Offset.Zero) }
    val zoom = rememberTransformableState { z, pan, _ ->
        scale = (scale * z).coerceIn(1f, 6f)
        offset = if (scale > 1f) offset + pan else Offset.Zero
    }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AsyncImage(model = ImageRequest.Builder(LocalContext.current)
            .data(m.url.ifBlank { m.preview }).placeholderMemoryCacheKey(m.preview)
            .crossfade(true).build(),
            contentDescription = m.alt.ifBlank { null }, contentScale = ContentScale.Fit,
            modifier = Modifier.fillMaxSize()
                .pointerInput(index) {
                    detectTapGestures(onDoubleTap = { scale = 1f; offset = Offset.Zero })
                }
                .transformable(zoom)
                .graphicsLayer(scaleX = scale, scaleY = scale,
                    translationX = offset.x, translationY = offset.y))
        val moving = m.kind == "video" || m.kind == "gifv" || m.kind == "audio"
        if (moving && m.url.isNotBlank()) {
            IconButton(onClick = { openBrowser(m.url) },
                modifier = Modifier.align(Alignment.Center).size(72.dp).clip(CircleShape)
                    .background(Color(0x99000000))) {
                Icon(Icons.Filled.PlayArrow, stringResource(R.string.play), tint = Color.White,
                    modifier = Modifier.size(40.dp))
            }
        }
        Column(Modifier.fillMaxSize().safeDrawingPadding()) {
            Row(Modifier.fillMaxWidth().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = close) {
                    Icon(Icons.Filled.Close, stringResource(R.string.close), tint = Color.White)
                }
                if (place.items.size > 1) {
                    Text("${index + 1} / ${place.items.size}", color = Color.White, fontSize = 14.sp)
                }
            }
            Row(Modifier.weight(1f).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween) {
                if (index > 0) {
                    IconButton(onClick = { index -= 1 }) {
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, null, tint = Color.White)
                    }
                } else Box(Modifier.size(48.dp))
                if (index < place.items.size - 1) {
                    IconButton(onClick = { index += 1 }) {
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = Color.White)
                    }
                }
            }
            if (m.alt.isNotBlank()) {
                Text(m.alt, color = Color.White, fontSize = 14.sp,
                    modifier = Modifier.fillMaxWidth().background(Color(0xAA000000))
                        .verticalScroll(rememberScrollState()).padding(16.dp))
            }
        }
    }
}
