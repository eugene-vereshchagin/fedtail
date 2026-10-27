package online.dmesg.fedtail

import android.graphics.ImageDecoder
import android.graphics.drawable.AnimatedImageDrawable
import android.widget.ImageView
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView

/** The opossum over an empty lane, as the windows' curtain: swinging while a poll round
 *  is on (the core says "busy"), standing otherwise — so an empty lane reads as nothing
 *  new, not as a dead network. The sticker's GIF (res/raw, from fedtail/data/icons),
 *  drawn by Android's own AnimatedImageDrawable. */
@Composable
fun Possum(swinging: Boolean, modifier: Modifier = Modifier) {
    AndroidView(
        modifier = modifier.size(96.dp),
        factory = { context ->
            ImageView(context).apply {
                val d = ImageDecoder.decodeDrawable(
                    ImageDecoder.createSource(context.resources, R.raw.possum_swing))
                setImageDrawable(d)
                importantForAccessibility = ImageView.IMPORTANT_FOR_ACCESSIBILITY_NO
            }
        },
        update = { view ->
            (view.drawable as? AnimatedImageDrawable)?.let {
                if (swinging) {
                    // over and over while the round is on (busy again while running out:
                    // it simply goes on)
                    it.repeatCount = AnimatedImageDrawable.REPEAT_INFINITE
                    if (!it.isRunning) it.start()
                } else if (it.isRunning) {
                    // the round is over: this swing runs to its end — back where the
                    // sticker stands still — and stops there, not mid-swing
                    it.repeatCount = 0
                }
            }
        })
}
