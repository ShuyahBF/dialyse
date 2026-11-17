package com.shuyah.dialyse

import android.webkit.JavascriptInterface
import org.json.JSONObject

/**
 * PONT entre le site Dialyse et le téléphone : l'objet « window.DialyseAndroid » du JavaScript du site. Seules les pages de Dialyse (site et API)
 * se chargent dans la fenêtre, donc seules elles peuvent l'appeler.
 *
 * Pour un développeur WinDev : c'est l'équivalent d'une DLL appelée par le site. Chaque fonction annotée @JavascriptInterface est visible du site.
 */
class Pont(private val activite: WebActivity) {
    /** Description de l'application : version, verrou disponible, notifications possibles. */
    @JavascriptInterface
    fun capacites(): String = JSONObject().put("application", true).put("version", BuildConfig.VERSION_NAME)
        .put("verrou_disponible", Verrou.disponible(activite)).toString()

    /** Recharge le site (bouton « Réessayer » de la page « Pas de connexion »). */
    @JavascriptInterface
    fun reessayer() { activite.runOnUiThread { activite.recharger() } }

    /** Les notifications sont-elles activées sur ce téléphone ? */
    @JavascriptInterface
    fun notificationsActives(): Boolean = Alertes.actives(activite)

    /** Active les notifications : range le jeton de lecture (chiffré) et l'adresse de l'API, puis demande l'autorisation de notifier (Android 13+). */
    @JavascriptInterface
    fun notificationsActiver(adresseApi: String, jeton: String) {
        // Le jeton n'est envoyé qu'au serveur Dialyse de l'application (jamais à une autre adresse)
        if (android.net.Uri.parse(adresseApi).host != android.net.Uri.parse(BuildConfig.API_URL).host) return
        Alertes.activer(activite, adresseApi, jeton)
        activite.runOnUiThread { activite.demanderAutorisationNotifications() }
    }

    /** Arrête les notifications et oublie le jeton. */
    @JavascriptInterface
    fun notificationsDesactiver() { Alertes.desactiver(activite) }
}
