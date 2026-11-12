package online.dmesg.fedtail

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** A text file attached to a post (common/links.file_link), read here, as the windows'
 *  TextFile: its name on top, its words (selectable) below — "loading" till they come
 *  (text null); "Open in the browser" for the file itself. */
@Composable
fun TextFileScreen(place: Place.TextFile, text: String?, close: () -> Unit,
                   openBrowser: (String) -> Unit) {
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().safeDrawingPadding()) {
            Row(Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text("📄 " + place.name, fontWeight = FontWeight.Medium, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                TextButton(onClick = { openBrowser(place.url) }) {
                    Text(stringResource(R.string.open_browser), fontSize = 13.sp)
                }
                IconButton(onClick = close) {
                    Icon(Icons.Filled.Close, stringResource(R.string.close))
                }
            }
            SelectionContainer(Modifier.weight(1f).verticalScroll(rememberScrollState())
                .padding(horizontal = 12.dp, vertical = 8.dp)) {
                Text(text ?: stringResource(R.string.loading), fontFamily = FontFamily.Monospace,
                    fontSize = 13.sp, lineHeight = 18.sp,
                    color = MaterialTheme.colorScheme.onSurface)
            }
        }
    }
}
