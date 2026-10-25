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
import androidx.compose.foundation.layout.size

/**
 * The look of the mockups' variant A ("calm"): a cool grey ground, white cards, one blue
 * accent, and an orange one for what is addressed to you — ui.theme = "system". Any
 * other of fedtail's themes paints the phone with its own colours (themeScheme).
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

/** colors: the theme's (bridge.theme: bg, card, text, muted, line, accent, accent-text,
 *  danger…); null or empty — the phone's own light or dark in the calm colours. */
@Composable
fun FedtailTheme(colors: Map<String, String>? = null, light: Boolean = true,
                 font: androidx.compose.ui.text.font.FontFamily? = null, postScale: Float = 1f,
                 pictures: Map<String, ThemePic> = emptyMap(),
                 content: @Composable () -> Unit) {
    val scheme = colors?.takeIf { it.isNotEmpty() }?.let { themeScheme(it, light) }
        ?: if (isSystemInDarkTheme()) Dark else Light
    val type = androidx.compose.material3.Typography().let { t -> font?.let { t.inFamily(it) } ?: t }
    androidx.compose.runtime.CompositionLocalProvider(LocalPictures provides pictures,
        LocalPostScale provides postScale) {
        MaterialTheme(colorScheme = scheme, typography = type, content = content)
    }
}

/** "#rrggbb" or "#rrggbbaa" → a colour; anything else (rgba(…)) — null. */
fun hexColor(text: String?): Color? {
    val t = text?.trim() ?: return null
    if (!Regex("#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?").matches(t)) return null
    val rgb = t.substring(1, 7).toLong(16)
    val a = if (t.length == 9) t.substring(7, 9).toLong(16) else 0xFF
    return Color((a shl 24 or rgb).toInt())
}

private fun mix(a: Color, b: Color, part: Float) = Color(
    red = a.red + (b.red - a.red) * part, green = a.green + (b.green - a.green) * part,
    blue = a.blue + (b.blue - a.blue) * part, alpha = 1f)

/** One of fedtail's themes as Material's roles: the page, the cards, the words, the
 *  accent; containers mixed from them, so every screen follows the theme. */
fun themeScheme(c: Map<String, String>, light: Boolean): androidx.compose.material3.ColorScheme {
    val base = if (light) Light else Dark
    val bg = hexColor(c["bg"]) ?: base.background
    val text = hexColor(c["text"]) ?: base.onBackground
    val card = hexColor(c["card"]) ?: bg
    val muted = hexColor(c["muted"]) ?: mix(text, bg, 0.4f)
    val line = hexColor(c["line"]) ?: mix(text, bg, 0.8f)
    val accent = hexColor(c["accent"]) ?: base.primary
    val onAccent = hexColor(c["accent-text"]) ?: if (light) Color.White else Color.Black
    val hot = hexColor(c["danger"]) ?: base.secondary
    val variant = mix(card, text, 0.06f)
    return base.copy(
        primary = accent, onPrimary = onAccent,
        primaryContainer = mix(card, accent, 0.18f), onPrimaryContainer = text,
        secondary = hot, onSecondary = onAccent,
        secondaryContainer = mix(card, hot, 0.18f), onSecondaryContainer = text,
        background = bg, onBackground = text,
        surface = card, onSurface = text,
        surfaceVariant = variant, onSurfaceVariant = muted,
        surfaceContainer = card, surfaceContainerLow = card,
        surfaceContainerHigh = mix(card, text, 0.04f), surfaceContainerHighest = variant,
        outline = line, outlineVariant = mix(line, card, 0.5f),
    )
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

// ---- a theme's font and pictures ------------------------------------------------------

/** A theme's own picture for a button: SVG text (coloured already) or a PNG file. */
data class ThemePic(val svg: String = "", val png: String = "")

/** The theme's pictures by the app's word (reply, boost, like, more…); {} — Material's. */
val LocalPictures = androidx.compose.runtime.staticCompositionLocalOf { emptyMap<String, ThemePic>() }

/** How much larger a post's words are than the rest ([font] post_scale). */
val LocalPostScale = androidx.compose.runtime.staticCompositionLocalOf { 1f }

/** The theme's font files (bridge.theme "font"): regular, bold, italic, bold_italic. */
fun fontFamilyOf(files: Map<String, String>?): androidx.compose.ui.text.font.FontFamily? {
    if (files == null || files["regular"] == null) return null
    return try {
        val fonts = files.mapNotNull { (key, path) ->
            val file = java.io.File(path)
            if (!file.isFile) return@mapNotNull null
            val weight = if (key.startsWith("bold")) androidx.compose.ui.text.font.FontWeight.Bold
                         else androidx.compose.ui.text.font.FontWeight.Normal
            val style = if (key.endsWith("italic")) androidx.compose.ui.text.font.FontStyle.Italic
                        else androidx.compose.ui.text.font.FontStyle.Normal
            androidx.compose.ui.text.font.Font(file, weight, style)
        }
        if (fonts.isEmpty()) null else androidx.compose.ui.text.font.FontFamily(fonts)
    } catch (e: Exception) {
        null
    }
}

/** Every style of Material's typography in the theme's family. */
fun androidx.compose.material3.Typography.inFamily(f: androidx.compose.ui.text.font.FontFamily) =
    androidx.compose.material3.Typography(
        displayLarge = displayLarge.copy(fontFamily = f), displayMedium = displayMedium.copy(fontFamily = f),
        displaySmall = displaySmall.copy(fontFamily = f), headlineLarge = headlineLarge.copy(fontFamily = f),
        headlineMedium = headlineMedium.copy(fontFamily = f), headlineSmall = headlineSmall.copy(fontFamily = f),
        titleLarge = titleLarge.copy(fontFamily = f), titleMedium = titleMedium.copy(fontFamily = f),
        titleSmall = titleSmall.copy(fontFamily = f), bodyLarge = bodyLarge.copy(fontFamily = f),
        bodyMedium = bodyMedium.copy(fontFamily = f), bodySmall = bodySmall.copy(fontFamily = f),
        labelLarge = labelLarge.copy(fontFamily = f), labelMedium = labelMedium.copy(fontFamily = f),
        labelSmall = labelSmall.copy(fontFamily = f))

/** A button's picture: the theme's own (drawn as it is), else the Material icon, tinted. */
@Composable
fun ThemedIcon(
    word: String, fallback: ImageVector, description: String?,
    modifier: androidx.compose.ui.Modifier = androidx.compose.ui.Modifier,
    tint: Color = androidx.compose.material3.LocalContentColor.current,
) {
    val pic = LocalPictures.current[word]
    if (pic == null) {
        androidx.compose.material3.Icon(fallback, description, modifier, tint = tint)
        return
    }
    val context = androidx.compose.ui.platform.LocalContext.current
    val request = androidx.compose.runtime.remember(pic) {
        coil.request.ImageRequest.Builder(context).apply {
            if (pic.svg.isNotBlank()) {
                data(java.nio.ByteBuffer.wrap(pic.svg.toByteArray()))
                decoderFactory(coil.decode.SvgDecoder.Factory())
                memoryCacheKey("pic:" + pic.svg.hashCode())
            } else {
                data(java.io.File(pic.png))
            }
        }.build()
    }
    coil.compose.AsyncImage(model = request, contentDescription = description,
        modifier = modifier.then(androidx.compose.ui.Modifier.size(24.dp)))
}
