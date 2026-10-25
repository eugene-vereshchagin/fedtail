package online.dmesg.fedtail

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * The notification shade: the windows' notes (fedtail/frontends/notifytext.py — the same
 * words, notify.privacy, notify.lanes), one per lane, replaced as more come. While the app
 * is open the core's own rounds bring them; closed, a round every 15 minutes or so
 * (RoundWorker). A tap opens the thread (or the lane) the note is about.
 */
object Notifier {
    private const val CHANNEL = "news"
    const val EXTRA_THREAD = "note_thread"
    const val EXTRA_LANE = "note_lane"

    /** The newest note shown, as the core numbers them (this process's). -1: none asked yet. */
    @Volatile var lastSeq = -1
    /** The app is on screen: notes only with notify.when_focused. */
    @Volatile var visible = false

    fun channel(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java) ?: return
        if (nm.getNotificationChannel(CHANNEL) != null) return
        nm.createNotificationChannel(NotificationChannel(CHANNEL,
            context.getString(R.string.note_channel), NotificationManager.IMPORTANCE_DEFAULT))
    }

    fun allowed(context: Context) = ContextCompat.checkSelfPermission(context,
        Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /** What notes() or background_round() said: shown (unless it says not to), remembered. */
    fun take(context: Context, got: JSONObject) {
        if (got.has("error")) return
        lastSeq = got.optInt("n", lastSeq)
        if (!got.optBoolean("enabled", true)) return
        if (visible && !got.optBoolean("when_focused")) return
        show(context, got.optJSONArray("notes") ?: JSONArray())
    }

    private fun show(context: Context, notes: JSONArray) {
        if (notes.length() == 0 || !allowed(context)) return
        channel(context)
        val nm = NotificationManagerCompat.from(context)
        for (i in 0 until notes.length()) {
            val n = notes.getJSONObject(i)
            val lane = n.optString("lane")
            val thread = if (n.isNull("thread")) "" else n.optString("thread")
            val open = Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .putExtra(EXTRA_LANE, lane).putExtra(EXTRA_THREAD, thread)
            val id = lane.hashCode()  // one note a lane: the newest replaces the last
            val tap = PendingIntent.getActivity(context, id, open,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val body = n.optString("body")
            val note = NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_note)
                .setContentTitle(n.optString("title"))
                .setContentText(body)
                .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                .setContentIntent(tap)
                .setAutoCancel(true)
                .build()
            try {
                nm.notify(id, note)
            } catch (e: SecurityException) {
                return // the permission was taken back meanwhile
            }
        }
    }

    /** The background rounds: every 15 minutes (the system's least), with a network. */
    fun schedule(context: Context) {
        val work = PeriodicWorkRequestBuilder<RoundWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork("round",
            ExistingPeriodicWorkPolicy.KEEP, work)
    }
}

/** A round with the app closed (or out of sight): the core made if the process has none,
 *  the server asked once, what came — into the shade. Nothing while the app is on screen. */
class RoundWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        if (Notifier.visible || !Notifier.allowed(applicationContext)) return Result.success()
        val ready = Core.ready(applicationContext, Locale.getDefault().language)
        if (ready.has("error") || !ready.optBoolean("logged_in")) return Result.success()
        // a process the system made just for this round has said nothing yet: all of it
        val got = Core.backgroundRound(maxOf(Notifier.lastSeq, 0))
        Notifier.take(applicationContext, got)
        return Result.success()
    }
}
