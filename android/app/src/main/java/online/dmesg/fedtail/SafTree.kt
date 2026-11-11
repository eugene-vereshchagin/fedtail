package online.dmesg.fedtail

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import org.json.JSONArray

/**
 * Sync through a folder on the phone (sync.folder = a content:// address): Android 11+
 * lets an app into a shared folder only through the system's picker (11.11: a typed path
 * had no permission — Syncthing's folder couldn't be read). The picker's answer is kept
 * with a lasting permission (Places.kt), and this reads and writes it for the core — the
 * same few calls as core/sync/backends.LocalTree (bridge.py: backends.CONTENT_TREE).
 *
 * Paths are the journal's: "" (the top), "<device>", "<device>/<n>.fts", "media/<name>";
 * each piece is found among its folder's children by name. Errors come back as words:
 * [ready] says what is wrong ("" — all well), [read] and [list] give null for "not there".
 */
object SafTree {
    @Volatile var context: Context? = null

    private const val DIR = DocumentsContract.Document.MIME_TYPE_DIR

    private class Doc(val id: String, val name: String, val dir: Boolean)

    private fun resolver() = (context ?: error("no context")).contentResolver

    private fun children(tree: Uri, parent: String): List<Doc> {
        val uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parent)
        val cols = arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE)
        val out = mutableListOf<Doc>()
        resolver().query(uri, cols, null, null, null)?.use { c ->
            while (c.moveToNext()) {
                out += Doc(c.getString(0), c.getString(1) ?: "", c.getString(2) == DIR)
            }
        }
        return out
    }

    /** The document at `path` under the tree, or null when some piece isn't there. */
    private fun find(tree: Uri, path: String): Doc? {
        var cur = Doc(DocumentsContract.getTreeDocumentId(tree), "", true)
        for (piece in path.split('/').filter { it.isNotEmpty() }) {
            if (!cur.dir) return null
            cur = children(tree, cur.id).firstOrNull { it.name == piece } ?: return null
        }
        return cur
    }

    private fun uriOf(tree: Uri, doc: Doc) = DocumentsContract.buildDocumentUriUsingTree(tree, doc.id)

    private fun split(path: String): Pair<String, String> {
        val at = path.lastIndexOf('/')
        return if (at < 0) "" to path else path.substring(0, at) to path.substring(at + 1)
    }

    /** "" when the folder can be read and written; else why not, in words. */
    @JvmStatic fun ready(root: String): String = try {
        val tree = Uri.parse(root)
        val held = resolver().persistedUriPermissions.any {
            it.uri == tree && it.isReadPermission && it.isWritePermission }
        when {
            !held -> "no permission: choose the folder again"
            find(tree, "") == null -> "not there"
            else -> ""
        }
    } catch (e: Exception) {
        e.message ?: e.javaClass.simpleName
    }

    /** [[name, is a folder]…] as JSON, or null: no such folder. */
    @JvmStatic fun list(root: String, sub: String): String? {
        val tree = Uri.parse(root)
        val at = find(tree, sub) ?: return null
        if (!at.dir) return null
        val out = JSONArray()
        children(tree, at.id).forEach { out.put(JSONArray().put(it.name).put(it.dir)) }
        return out.toString()
    }

    @JvmStatic fun read(root: String, path: String): ByteArray? = try {
        val tree = Uri.parse(root)
        val doc = find(tree, path)
        if (doc == null || doc.dir) null
        else resolver().openInputStream(uriOf(tree, doc))?.use { it.readBytes() }
    } catch (e: Exception) {
        null  // gone, or still arriving: the next round
    }

    /** Written under a ".part" name and renamed: the others never see half a file. */
    @JvmStatic fun write(root: String, path: String, blob: ByteArray) {
        val tree = Uri.parse(root)
        val (sub, name) = split(path)
        val parent = find(tree, sub)?.takeIf { it.dir } ?: error("no folder $sub")
        val parentUri = uriOf(tree, parent)
        val kids = children(tree, parent.id)
        kids.firstOrNull { it.name == ".$name.part" }?.let {
            DocumentsContract.deleteDocument(resolver(), uriOf(tree, it)) }
        val part = DocumentsContract.createDocument(resolver(), parentUri,
            "application/octet-stream", ".$name.part") ?: error("can't create $path")
        resolver().openOutputStream(part, "wt")?.use { it.write(blob) } ?: error("can't write $path")
        kids.firstOrNull { it.name == name }?.let {
            DocumentsContract.deleteDocument(resolver(), uriOf(tree, it)) }
        val renamed = try {
            DocumentsContract.renameDocument(resolver(), part, name)
        } catch (e: Exception) {
            null
        }
        if (renamed == null) {  // a provider that can't rename: written in place
            DocumentsContract.deleteDocument(resolver(), part)
            val doc = DocumentsContract.createDocument(resolver(), parentUri,
                "application/octet-stream", name) ?: error("can't create $path")
            resolver().openOutputStream(doc, "wt")?.use { it.write(blob) }
                ?: error("can't write $path")
        }
    }

    @JvmStatic fun mkdir(root: String, sub: String) {
        val tree = Uri.parse(root)
        if (find(tree, sub)?.dir == true) return
        val (up, name) = split(sub)
        val parent = find(tree, up)?.takeIf { it.dir } ?: error("no folder $up")
        DocumentsContract.createDocument(resolver(), uriOf(tree, parent), DIR, name)
            ?: error("can't create $sub")
    }

    @JvmStatic fun delete(root: String, path: String) {
        val tree = Uri.parse(root)
        val doc = find(tree, path) ?: return
        DocumentsContract.deleteDocument(resolver(), uriOf(tree, doc))
    }
}
