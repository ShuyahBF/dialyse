package com.shuyah.dialyse

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.FragmentActivity
import org.json.JSONObject

/**
 * APPLICATION Dialyse : affiche le site Dialyse COMPLET (suivi anonymisé du DG et des médecins) dans une fenêtre intégrée, et lui donne accès au
 * téléphone par le pont `Pont` : verrou par empreinte (obligatoire) et notifications des nouvelles alertes.
 *
 * Pour un développeur WinDev : c'est un champ « navigateur » plein écran. Le site reste TOUJOURS à jour (rien à réinstaller quand on le modifie).
 * Hors connexion : page « Pas de connexion » avec « Réessayer ».
 *
 * Règles : seules les pages de Dialyse (site et API) se chargent dans la fenêtre ; tout autre lien s'ouvre dans le navigateur du téléphone ;
 * captures d'écran et aperçu dans les applications récentes INTERDITS (données de santé) ; le bouton Retour revient à la page précédente.
 */
class WebActivity : FragmentActivity() {
    private lateinit var web: WebView
    private lateinit var progression: ProgressBar
        private val adresseSite: Uri = Uri.parse(BuildConfig.SITE_URL)
    private val adresseApi: Uri = Uri.parse(BuildConfig.API_URL)

    // Autorisation de notifier (Android 13 et plus) : demandée une seule fois ; l'utilisateur peut la refuser sans perdre le reste de l'application
    private val demandeNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    /** Demande l'autorisation de notifier (Android 13 et plus) quand l'utilisateur réactive le réglage. */
    fun demanderAutorisationNotifications() { if (Build.VERSION.SDK_INT >= 33) demandeNotifications.launch(android.Manifest.permission.POST_NOTIFICATIONS) }

    /** Page de Dialyse demandée par une notification (ex. « suivi »), ou la page d'accueil. */
    /**
     * Connexion par Google : le navigateur du téléphone rappelle « dialyse://google?code=… » (ou « ?erreur=… », « ?lie=1 »).
     * On transforme ce rappel en page du site « /connexion-google?… », qui échange le code contre la session. Rend null si l'intention n'est pas ce rappel.
     */
    private fun urlRetourGoogle(i: Intent?): String? {
        val d = i?.data ?: return null
        if (d.scheme != "dialyse" || d.host != "google") return null
        return adresseSite.buildUpon().path("/connexion-google").encodedQuery(d.encodedQuery ?: "").build().toString()
    }

    private fun pageDemandee(i: Intent?): String {
        urlRetourGoogle(i)?.let { return it }
        val chemin = i?.getStringExtra(Alertes.EXTRA_OUVRIR)?.trim('/')?.takeIf { it.matches(Regex("[a-z0-9-]+")) }
        return if (chemin != null) adresseSite.toString().trimEnd('/') + "/" + chemin else adresseSite.toString()
    }

    /** Vrai pour une page de Dialyse (site ou API) : seules celles-ci restent dans la fenêtre et peuvent appeler le pont. */
    private fun estDialyse(u: Uri): Boolean {
        val h = u.host ?: return false
        val local = h == "10.0.2.2" || h == "localhost" || h == "127.0.0.1"       // essais locaux seulement
        return (u.scheme == "https" || (local && u.scheme == "http")) && (h == adresseSite.host || h == adresseApi.host)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Données de santé : ni capture d'écran, ni aperçu dans la liste des applications récentes
        window.setFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE, android.view.WindowManager.LayoutParams.FLAG_SECURE)
        web = WebView(this)
        progression = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 100; visibility = View.GONE }
        // Bande bleu nuit sous la barre d'état, puis le site
        val bandeHaut = View(this).apply { setBackgroundColor(Color.parseColor("#0A1E3D")) }
        val zoneSite = FrameLayout(this).apply {
            addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            addView(progression, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 8))
        }
        val racine = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#F3F5F9"))
            addView(bandeHaut, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0))
            addView(BandeauMiseAJourVue.creer(this@WebActivity), LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))   // nouvelle version dans ShuyahStore (v1.2)
            addView(zoneSite, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        }
        setContentView(racine)
        WindowCompat.getInsetsController(window, racine).isAppearanceLightStatusBars = false
        ViewCompat.setOnApplyWindowInsetsListener(racine) { vue, insets ->
            val barres = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            bandeHaut.layoutParams = bandeHaut.layoutParams.apply { height = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top }
            vue.setPadding(barres.left, 0, barres.right, barres.bottom)
            WindowInsetsCompat.CONSUMED
        }

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            userAgentString = userAgentString + " DialyseAndroid/" + BuildConfig.VERSION_NAME
        }
        // Le site et l'API ont deux adresses différentes
        CookieManager.getInstance().apply { setAcceptCookie(true); setAcceptThirdPartyCookies(web, true) }
        web.addJavascriptInterface(Pont(this), "DialyseAndroid")

        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val u = request.url
                if (estDialyse(u) || u.scheme == "file" || u.scheme == "about") return false
                ouvrirAilleurs(u); return true
            }
            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) { progression.visibility = View.VISIBLE }
            override fun onPageFinished(view: WebView, url: String?) { progression.visibility = View.GONE }
            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) view.loadUrl("file:///android_asset/hors_ligne.html")
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, nouveau: Int) { progression.progress = nouveau }
        }
        // Fichiers que le site voudrait faire enregistrer : une fenêtre intégrée ne sait pas les enregistrer
        web.setDownloadListener { url, _, _, _, _ ->
            if (url.startsWith("http")) ouvrirAilleurs(Uri.parse(url))
            else Toast.makeText(this, "Pour enregistrer ce fichier, ouvrez Dialyse dans le navigateur du téléphone.", Toast.LENGTH_LONG).show()
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() { if (web.canGoBack()) web.goBack() else finish() }
        })

        if (savedInstanceState != null) web.restoreState(savedInstanceState) else web.loadUrl(pageDemandee(intent))
        // Notifications d'alertes : tâche planifiée rejouée si elles sont activées (après une mise à jour de l'application, par exemple)
        if (Alertes.actives(this)) Alertes.planifier(this)
    }

    private fun ouvrirAilleurs(u: Uri) {
        try { startActivity(Intent(Intent.ACTION_VIEW, u)) } catch (_: ActivityNotFoundException) { Toast.makeText(this, "Aucune application pour ouvrir ce lien.", Toast.LENGTH_SHORT).show() }
    }

    // Clic sur une notification : la page « suivi » s'ouvre
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        urlRetourGoogle(intent)?.let { web.loadUrl(it) }                    // retour de Google (l'application était déjà ouverte)
        if (intent.hasExtra(Alertes.EXTRA_OUVRIR)) web.loadUrl(pageDemandee(intent))
    }

    // ------------------------------------------------------------------ verrou par empreinte (si l'utilisateur l'a activé)
    private var derniereOuverture = 0L
    private var verrouEnCours = false
    private fun verrouiller() {
        if (verrouEnCours) return
        // Aucun verrouillage d'écran sur le téléphone : l'application refuse de s'ouvrir (données de santé)
        if (!Verrou.disponible(this)) {
            web.visibility = View.INVISIBLE
            Toast.makeText(this, "Dialyse exige un verrouillage d'écran (empreinte, code ou schéma) : activez-le dans les réglages du téléphone.", Toast.LENGTH_LONG).show(); finish(); return
        }
        // Retour dans la minute (autorisation de notifier, lien externe…) : pas de nouvelle demande
        if (derniereOuverture != 0L && System.currentTimeMillis() - derniereOuverture < 60_000) { web.visibility = View.VISIBLE; return }
        verrouEnCours = true; web.visibility = View.INVISIBLE
        Verrou.verifier(this, "Ouvrir Dialyse", "Posez votre doigt pour continuer",
            surOk = { verrouEnCours = false; derniereOuverture = System.currentTimeMillis(); web.visibility = View.VISIBLE },
            surEchec = { message -> verrouEnCours = false; Toast.makeText(this, "Dialyse est verrouillé : $message", Toast.LENGTH_LONG).show(); finish() })
    }
    override fun onStop() { super.onStop(); if (!verrouEnCours) derniereOuverture = System.currentTimeMillis() }
    override fun onStart() { super.onStart(); verrouiller() }

    override fun onResume() { super.onResume(); Presence.signaler(this) }          // règle 4 : présence auprès de SAWALI
    override fun onSaveInstanceState(sortie: Bundle) { super.onSaveInstanceState(sortie); web.saveState(sortie) }
    override fun onDestroy() { web.destroy(); super.onDestroy() }

    /** Recharge le site (bouton « Réessayer » de la page « Pas de connexion »). */
    fun recharger() { web.loadUrl(adresseSite.toString()) }

    /** Envoie une réponse au site : window.dialyseRetour[id](json). Texte échappé par JSONObject.quote, jamais concaténé tel quel. */
    fun retour(id: String, json: JSONObject) {
        val script = "window.dialyseRetour && window.dialyseRetour[${JSONObject.quote(id)}] && window.dialyseRetour[${JSONObject.quote(id)}](${JSONObject.quote(json.toString())});"
        runOnUiThread { web.evaluateJavascript(script, null) }
    }
}
