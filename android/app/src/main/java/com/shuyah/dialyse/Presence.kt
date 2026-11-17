package com.shuyah.dialyse

import android.content.Context
import android.os.Build
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/**
 * Signal de présence auprès de SAWALI (règle 4 du propriétaire) : POST …/api/presence-logiciel au lancement, puis au plus toutes les
 * 5 minutes quand l'application revient au premier plan. Envoi en arrière-plan, JAMAIS bloquant ; aucune donnée personnelle
 * (seulement le modèle de l'appareil et la version).
 *
 * Pour un développeur WinDev : l'équivalent de la procédure « SignalPresenceSawali » appelée par un « TimerSys ».
 */
object Presence {
    private const val URL_PRESENCE = "https://api.sawalismartsystems.com/api/presence-logiciel"
    private const val INTERVALLE_MS = 5 * 60 * 1000L
    @Volatile private var dernierEnvoiMs = 0L
    private val demarreLe: String = isoUtc(Date())
    private val client: OkHttpClient by lazy { OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(10, TimeUnit.SECONDS).build() }

    private fun isoUtc(d: Date): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.format(d)

    /** Envoie un signal si le dernier date de plus de 5 minutes. Rend la main immédiatement ; toute erreur est ignorée. */
    @Suppress("UNUSED_PARAMETER")
    fun signaler(contexte: Context) {
        val maintenant = System.currentTimeMillis()
        if (maintenant - dernierEnvoiMs < INTERVALLE_MS) return
        runCatching {
            dernierEnvoiMs = maintenant
            val corps = JSONObject().apply {
                put("application", "dialyse-android")
                put("version", BuildConfig.VERSION_NAME)
                put("deploye_le", BuildConfig.DATE_BUILD)
                put("machine", "${Build.MANUFACTURER} ${Build.MODEL}".trim().take(100))
                put("site", "dialyse")
                put("systeme", "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
                put("demarre_le", demarreLe)
            }
            val requete = Request.Builder().url(URL_PRESENCE).post(corps.toString().toRequestBody("application/json; charset=utf-8".toMediaType())).build()
            client.newCall(requete).enqueue(object : Callback {       // enqueue = envoi asynchrone
                override fun onFailure(call: Call, e: IOException) {}
                override fun onResponse(call: Call, response: Response) { response.close() }
            })
        }
    }
}
