package online.dmesg.fedtail

import android.content.Context
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.unifiedpush.android.connector.FailedReason
import org.unifiedpush.android.connector.PushService
import org.unifiedpush.android.connector.UnifiedPush
import org.unifiedpush.android.connector.data.PushEndpoint
import org.unifiedpush.android.connector.data.PushMessage
import java.util.Locale

/**
 * Notifications at once with the app closed, without Google: UnifiedPush (phone.push).
 * A distributor the user installed (ntfy, Sunup, NextPush…) gives an address; the server
 * is subscribed to it (Web Push, encrypted to the connector's keys) and pushes there; a
 * push only wakes the app for a round — the notes are the windows' own (Notifier), so
 * notify.lanes and notify.privacy hold as everywhere. No distributor: the rounds every
 * 15 minutes go on as they did.
 */
object Push {
    /** After the screens opened: on (registered with the distributor) or off. */
    fun setUp(context: Context, mode: String) {
        try {
            if (mode == "off") {
                if (UnifiedPush.getAckDistributor(context) != null) UnifiedPush.unregister(context)
                return
            }
            val distributor = UnifiedPush.getAckDistributor(context)
                ?: UnifiedPush.getDistributors(context).firstOrNull()?.also {
                    UnifiedPush.saveDistributor(context, it)
                }
                ?: return // none on this phone: the rounds every 15 minutes do it
            UnifiedPush.register(context)
        } catch (e: Exception) {
            android.util.Log.w("fedtail", "push: $e")
        }
    }

    /** A push came: a round now (expedited, one at a time — a burst makes one round). */
    fun roundNow(context: Context) {
        val work = OneTimeWorkRequestBuilder<RoundWorker>()
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork("push-round", ExistingWorkPolicy.KEEP, work)
    }
}

/** What the distributor hands in: a new address (the server told), a push, a goodbye. */
class PushReceiver : PushService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewEndpoint(endpoint: PushEndpoint, instance: String) {
        val keys = endpoint.pubKeySet ?: return // no Web Push keys: the server can't encrypt
        scope.launch {
            val ready = Core.ready(applicationContext, Locale.getDefault().language)
            if (!ready.optBoolean("logged_in")) return@launch
            val got = Core.pushOn(endpoint.url, keys.pubKey, keys.auth)
            Core.failed(got)?.let { android.util.Log.w("fedtail", "push: $it") }
        }
    }

    override fun onMessage(message: PushMessage, instance: String) {
        Push.roundNow(applicationContext)
    }

    override fun onRegistrationFailed(reason: FailedReason, instance: String) {
        android.util.Log.i("fedtail", "push: registration failed: $reason")
    }

    override fun onUnregistered(instance: String) {
        scope.launch {
            val ready = Core.ready(applicationContext, Locale.getDefault().language)
            if (ready.optBoolean("logged_in")) Core.pushOff()
        }
    }
}
