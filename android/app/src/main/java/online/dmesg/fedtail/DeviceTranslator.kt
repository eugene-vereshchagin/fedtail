package online.dmesg.fedtail

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import dev.davidv.translator.ErrorType
import dev.davidv.translator.ITranslationCallback
import dev.davidv.translator.ITranslationService
import dev.davidv.translator.TranslationError
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * The phone's own translator: the Offline Translator app (F-Droid: dev.davidv.translator,
 * Bergamot's models, no network), through the API it gives other apps (its AIDL, MIT).
 * The core calls [translate] from its own threads (bridge.py: core/translate.DEVICE when
 * feed.translate_backend = "device") and waits; what to translate, the core decides.
 *
 * Errors come back as words the bridge turns into the user's language: "missing" (no
 * such app), "unknown" (it couldn't tell the language), "lang:<name>" (a language it has
 * no model for), anything else as it is.
 */
object DeviceTranslator {
    const val PACKAGE = "dev.davidv.translator"
    private const val ACTION = "dev.davidv.translator.ITranslationService"

    @Volatile var context: Context? = null
    @Volatile private var service: ITranslationService? = null
    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            service = ITranslationService.Stub.asInterface(binder)
            bound?.countDown()
        }
        override fun onServiceDisconnected(name: ComponentName?) { service = null }
        override fun onBindingDied(name: ComponentName?) { service = null; unbind() }
    }
    @Volatile private var bound: CountDownLatch? = null

    /** Whether the app is there at all (the settings say so before any translation). */
    @JvmStatic fun available(): Boolean = try {
        context?.packageManager?.getPackageInfo(PACKAGE, 0) != null
    } catch (_: Exception) { false }

    private fun unbind() {
        try { context?.unbindService(connection) } catch (_: Exception) {}
        service = null
        bound = null
    }

    @Synchronized private fun connect(timeoutMs: Long): ITranslationService {
        service?.let { if (it.asBinder().isBinderAlive) return it }
        val ctx = context ?: throw IllegalStateException("missing")
        if (!available()) throw IllegalStateException("missing")
        val latch = CountDownLatch(1)
        bound = latch
        val intent = Intent(ACTION).setPackage(PACKAGE)
        if (!ctx.bindService(intent, connection, Context.BIND_AUTO_CREATE)) {
            unbind()
            throw IllegalStateException("missing")
        }
        latch.await(timeoutMs, TimeUnit.MILLISECONDS)
        return service ?: throw IllegalStateException("the translator didn't answer")
    }

    /** [text] from [from] ("" — it finds out) into [to], waiting at most [timeoutMs]. */
    @JvmStatic fun translate(text: String, from: String, to: String, timeoutMs: Long): String {
        val svc = connect(minOf(timeoutMs, 10_000))
        val done = CountDownLatch(1)
        var result: String? = null
        var error: String? = null
        svc.translate(text, from, to, object : ITranslationCallback.Stub() {
            override fun onTranslationResult(translatedText: String?) {
                result = translatedText ?: ""
                done.countDown()
            }
            override fun onTranslationError(e: TranslationError?) {
                error = when (e?.type) {
                    ErrorType.COULD_NOT_DETECT_LANGUAGE -> "unknown"
                    ErrorType.DETECTED_BUT_UNAVAILABLE -> "lang:" + (e.language ?: "?")
                    else -> e?.message ?: "unexpected"
                }
                done.countDown()
            }
        })
        if (!done.await(timeoutMs, TimeUnit.MILLISECONDS)) throw IllegalStateException("timeout")
        error?.let { throw IllegalStateException(it) }
        return result ?: ""
    }
}
