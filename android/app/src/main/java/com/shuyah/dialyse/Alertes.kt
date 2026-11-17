package com.shuyah.dialyse

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.core.app.NotificationCompat
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * NOTIFICATIONS DES NOUVELLES ALERTES. Toutes les 15 minutes environ (minimum d'Android), même application fermée, le téléphone interroge le serveur Dialyse
 * avec un JETON DE LECTURE (il ne donne accès qu'au flux d'alertes ANONYMISÉES : code patient et motif, jamais un nom) et notifie ce qui est nouveau.
 *
 * Pour un développeur WinDev : une « tâche planifiée » d'Android (JobScheduler) qui se réveille toute seule quand le téléphone a du réseau.
 *
 * Sécurité : le jeton est rangé CHIFFRÉ (clé du coffre Android, jamais exportable) ; l'utilisateur peut tout couper depuis l'écran « Suivi anonymisé » ;
 * sur l'écran verrouillé, la notification ne montre qu'un texte neutre (le détail avec le code patient n'apparaît qu'après déverrouillage) ;
 * chaque alerte n'est notifiée qu'une seule fois (identifiants stables fournis par le serveur) ; à l'activation, les alertes déjà existantes sont
 * mémorisées SANS notification (elles se lisent dans l'application).
 */
object Alertes {
    private const val FICHIER = "alertes"
    private const val ID_JOB = 5301
    private const val CANAL = "alertes_dialyse"
    private const val ALIAS = "dialyse_jeton_alertes"
    const val EXTRA_OUVRIR = "ouvrir"
    private const val PERIODE_MS = 15L * 60 * 1000

    private fun prefs(c: Context) = c.getSharedPreferences(FICHIER, Context.MODE_PRIVATE)

    // ---------------------------------------------------------------- jeton chiffré (AES-GCM, clé du coffre Android)
    private fun cle(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build()
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply { init(spec) }.generateKey()
    }

    private fun chiffrer(texte: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, cle()) }
        return Base64.encodeToString(c.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(c.doFinal(texte.toByteArray()), Base64.NO_WRAP)
    }

    private fun dechiffrer(rangee: String?): String? = try {
        val (iv, donnees) = rangee!!.split(":")
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, cle(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP))) }
        String(c.doFinal(Base64.decode(donnees, Base64.NO_WRAP)))
    } catch (_: Exception) { null }

    // ---------------------------------------------------------------- réglage
    /** Notifications activées sur ce téléphone (un jeton est rangé). */
    fun actives(c: Context): Boolean = prefs(c).getString("jeton", null) != null

    /** Active : range l'adresse du serveur et le jeton (chiffré), repart d'une liste vide (la première vérification mémorise l'existant sans notifier). */
    fun activer(c: Context, adresseApi: String, jeton: String) {
        prefs(c).edit().putString("jeton", chiffrer(jeton)).putString("api", adresseApi.trimEnd('/')).remove("connues").apply()
        planifier(c)
    }

    fun desactiver(c: Context) { prefs(c).edit().clear().apply(); annuler(c) }

    fun permissionDemandee(c: Context) = prefs(c).getBoolean("permission_demandee", false)
    fun permissionMarquee(c: Context) { prefs(c).edit().putBoolean("permission_demandee", true).apply() }

    /** Autorisation de notifier (Android 13 et plus la demande à l'utilisateur ; avant, elle est automatique). */
    fun peutNotifier(c: Context) = Build.VERSION.SDK_INT < 33 || c.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /** Planifie la vérification périodique (une seule tâche, rejouée au redémarrage du téléphone). Sans effet si elle existe déjà. */
    fun planifier(c: Context) {
        val js = c.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler
        if (js.allPendingJobs.any { it.id == ID_JOB }) return
        js.schedule(JobInfo.Builder(ID_JOB, ComponentName(c, JobAlertes::class.java)).setPeriodic(PERIODE_MS)
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPersisted(true).build())
    }
    private fun annuler(c: Context) { (c.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler).cancel(ID_JOB) }

    // ---------------------------------------------------------------- vérification
    /** Flux anonymisé du serveur (ou null si le serveur ne répond pas ; 401 : jeton retiré par le serveur, les notifications s'arrêtent). */
    private fun lireFlux(c: Context): JSONArray? {
        val jeton = dechiffrer(prefs(c).getString("jeton", null)) ?: return null
        val api = prefs(c).getString("api", null) ?: return null
        return try {
            val cx = URL("$api/anonyme/flux").openConnection() as HttpURLConnection
            cx.connectTimeout = 30000; cx.readTimeout = 60000; cx.setRequestProperty("X-Jeton-Alertes", jeton)
            when (cx.responseCode) {
                200 -> JSONObject(cx.inputStream.bufferedReader().readText()).optJSONArray("alertes")
                401 -> { desactiver(c); null }
                else -> null
            }
        } catch (_: Exception) { null }
    }

    /** Vérifie et notifie ce qui n'a pas déjà été annoncé. Rend le nombre d'alertes nouvellement annoncées (appelé hors du fil principal). */
    fun verifierEtNotifier(c: Context): Int {
        if (!actives(c)) return 0
        val flux = lireFlux(c) ?: return 0
        val toutes = (0 until flux.length()).mapNotNull { flux.optJSONObject(it) }
        val connues = prefs(c).getStringSet("connues", null)
        val ids = toutes.map { it.optString("id") }.toSet()
        prefs(c).edit().putStringSet("connues", ids).apply()                   // ne garde que les alertes encore d'actualité
        if (connues == null) return 0                                          // première vérification : l'existant est mémorisé sans notification
        val nouvelles = toutes.filter { it.optString("id") !in connues }
        if (nouvelles.isEmpty() || !peutNotifier(c)) return 0
        notifier(c, nouvelles)
        return nouvelles.size
    }

    private fun notifier(c: Context, nouvelles: List<JSONObject>) {
        val nm = c.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(NotificationChannel(CANAL, "Alertes Dialyse", NotificationManager.IMPORTANCE_HIGH))
        val ouvrir = Intent(c, WebActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP).putExtra(EXTRA_OUVRIR, "suivi")
        val clic = PendingIntent.getActivity(c, 0, ouvrir, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val critiques = nouvelles.count { it.optString("gravite") == "critique" }
        val titre = (if (critiques > 0) "$critiques alerte(s) critique(s)" else "${nouvelles.size} nouvelle(s) alerte(s)") + " — Dialyse"
        // Détail : code patient (ou « Stock ») et motif, sans aucune identité ; au plus 5 lignes
        val lignes = nouvelles.sortedBy { if (it.optString("gravite") == "critique") 0 else 1 }.take(5)
            .map { (it.optString("code").takeIf { code -> code.isNotBlank() && code != "null" } ?: "Stock") + " : " + it.optString("message") }
        // Sur l'écran verrouillé : texte neutre seulement (VISIBILITY_PRIVATE + version publique)
        val publique = NotificationCompat.Builder(c, CANAL).setSmallIcon(android.R.drawable.stat_notify_error).setContentTitle("Dialyse").setContentText("Nouvelle alerte : déverrouillez pour la lire").build()
        val n = NotificationCompat.Builder(c, CANAL).setSmallIcon(android.R.drawable.stat_notify_error).setContentTitle(titre).setContentText(lignes.first())
            .setStyle(NotificationCompat.InboxStyle().also { s -> lignes.forEach { s.addLine(it) } }).setContentIntent(clic).setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH).setVisibility(NotificationCompat.VISIBILITY_PRIVATE).setPublicVersion(publique).build()
        nm.notify(ID_JOB, n)
    }

    /** Tâche planifiée : s'exécute dans un fil à part (jamais sur le fil principal), puis se déclare terminée. */
    class JobAlertes : JobService() {
        override fun onStartJob(p: JobParameters): Boolean {
            Thread { try { verifierEtNotifier(applicationContext) } catch (_: Exception) { /* réessai à la prochaine échéance */ } finally { jobFinished(p, false) } }.start()
            return true
        }
        override fun onStopJob(p: JobParameters) = true
    }
}
