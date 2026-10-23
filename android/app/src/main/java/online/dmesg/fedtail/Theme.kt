package online.dmesg.fedtail

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathBuilder
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

/**
 * The look of the mockups' variant A ("calm"): a cool grey ground, white cards, one blue
 * accent, and an orange one for what is addressed to you. Fixed colours, not the
 * wallpaper's: fedtail's themes come to the phone later, this is the default one.
 */
private val Light = lightColorScheme(
    primary = Color(0xFF1F5FA8), onPrimary = Color.White,
    primaryContainer = Color(0xFFE3ECF7), onPrimaryContainer = Color(0xFF174A85),
    secondary = Color(0xFFC2410C), onSecondary = Color.White,
    secondaryContainer = Color(0xFFFBE9DF), onSecondaryContainer = Color(0xFF7A2A08),
    tertiary = Color(0xFF2E7D4F), onTertiary = Color.White,
    background = Color(0xFFF3F5F7), onBackground = Color(0xFF1B1F24),
    surface = Color(0xFFFFFFFF), onSurface = Color(0xFF1B1F24),
    surfaceVariant = Color(0xFFEEF1F4), onSurfaceVariant = Color(0xFF5B6470),
    surfaceContainer = Color(0xFFFFFFFF), surfaceContainerLow = Color(0xFFFFFFFF),
    surfaceContainerHigh = Color(0xFFF7F8FA), surfaceContainerHighest = Color(0xFFEEF1F4),
    outline = Color(0xFFC9D0D8), outlineVariant = Color(0xFFE1E5EA),
    error = Color(0xFFB3261E),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF8AB4F0), onPrimary = Color(0xFF0B2A4D),
    primaryContainer = Color(0xFF1E3A5C), onPrimaryContainer = Color(0xFFD6E4F7),
    secondary = Color(0xFFF09060), onSecondary = Color(0xFF3A1505),
    secondaryContainer = Color(0xFF4A2412), onSecondaryContainer = Color(0xFFFBDCCB),
    tertiary = Color(0xFF7FCB9B), onTertiary = Color(0xFF0B2E18),
    background = Color(0xFF0F1317), onBackground = Color(0xFFE3E7EC),
    surface = Color(0xFF171C21), onSurface = Color(0xFFE3E7EC),
    surfaceVariant = Color(0xFF20262C), onSurfaceVariant = Color(0xFF9AA4AF),
    surfaceContainer = Color(0xFF171C21), surfaceContainerLow = Color(0xFF171C21),
    surfaceContainerHigh = Color(0xFF1D2329), surfaceContainerHighest = Color(0xFF20262C),
    outline = Color(0xFF3A434D), outlineVariant = Color(0xFF262D34),
    error = Color(0xFFF2B8B5),
)

@Composable
fun FedtailTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, content = content)
}

/** Avatars without a picture (or before it comes): a colour of the person's own. */
private val FACES = listOf(0xFF3B4A3F, 0xFF8A7448, 0xFF2F4F6F, 0xFF5A3D5C, 0xFF7A3B2E,
    0xFF2E6B6B, 0xFF5B5F2E, 0xFF4B4F7A)

fun faceColor(key: String): Color = Color(FACES[Math.floorMod(key.hashCode(), FACES.size)])

/** The few line icons Material's core set lacks (stroke, as in the mockups). */
object Glyphs {
    private fun stroke(name: String, block: PathBuilder.() -> Unit) =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).path(
            fill = null, stroke = SolidColor(Color.Black), strokeLineWidth = 2f,
            strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round,
            pathBuilder = block).build()

    val Reply: ImageVector = stroke("reply") {
        moveTo(9f, 14f); lineTo(4f, 9f); lineTo(9f, 4f)
        moveTo(4f, 9f); horizontalLineTo(14f)
        arcTo(6f, 6f, 0f, false, true, 20f, 15f); verticalLineTo(20f)
    }

    val Boost: ImageVector = stroke("boost") {
        moveTo(17f, 2f); lineTo(21f, 6f); lineTo(17f, 10f)
        moveTo(3f, 11f); verticalLineTo(10f)
        arcTo(4f, 4f, 0f, false, true, 7f, 6f); horizontalLineTo(21f)
        moveTo(7f, 22f); lineTo(3f, 18f); lineTo(7f, 14f)
        moveTo(21f, 13f); verticalLineTo(14f)
        arcTo(4f, 4f, 0f, false, true, 17f, 18f); horizontalLineTo(3f)
    }

    val Grid: ImageVector = stroke("lanes") {
        moveTo(4f, 4f); horizontalLineTo(10f); verticalLineTo(10f); horizontalLineTo(4f); close()
        moveTo(14f, 4f); horizontalLineTo(20f); verticalLineTo(10f); horizontalLineTo(14f); close()
        moveTo(4f, 14f); horizontalLineTo(10f); verticalLineTo(20f); horizontalLineTo(4f); close()
        moveTo(14f, 14f); horizontalLineTo(20f); verticalLineTo(20f); horizontalLineTo(14f); close()
    }

    val Done: ImageVector = stroke("done") {
        moveTo(5f, 12f); lineTo(10f, 17f); lineTo(19f, 7f)
    }
}
