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
import androidx.compose.runtime.DisposableEffect
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
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.foundation.layout.Spacer
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest

/**
 * A post's pictures over everything: black, one at a time (‹ › between them), pinch to
 * zoom, a double tap back to whole; the description (alt) below. A video or a sound
 * plays right here (Media3: straight from its server, never with the token); a gif
 * loops silently, as the windows play it. ↗ hands it to the browser all the same.
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
            MediaPlayer(m.url, gif = m.kind == "gifv", key = index)
        }
        Column(Modifier.fillMaxSize().safeDrawingPadding()) {
            Row(Modifier.fillMaxWidth().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = close) {
                    Icon(Icons.Filled.Close, stringResource(R.string.close), tint = Color.White)
                }
                if (place.items.size > 1) {
                    Text("${index + 1} / ${place.items.size}", color = Color.White, fontSize = 14.sp)
                }
                Spacer(Modifier.weight(1f))
                if (m.url.isNotBlank()) {
                    IconButton(onClick = { openBrowser(m.url) }) {
                        Text("↗", color = Color.White, fontSize = 20.sp)
                    }
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

/** One video, gif or sound: plays when shown, stops and lets go when left. */
@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@Composable
private fun MediaPlayer(url: String, gif: Boolean, key: Int) {
    val context = LocalContext.current
    val player = remember(url, key) {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(url))
            repeatMode = if (gif) Player.REPEAT_MODE_ALL else Player.REPEAT_MODE_OFF
            volume = if (gif) 0f else 1f
            playWhenReady = true
            prepare()
        }
    }
    DisposableEffect(player) { onDispose { player.release() } }
    AndroidView(modifier = Modifier.fillMaxSize(), factory = { ctx ->
        PlayerView(ctx).apply {
            this.player = player
            useController = !gif
            setShutterBackgroundColor(android.graphics.Color.TRANSPARENT)
        }
    })
}
