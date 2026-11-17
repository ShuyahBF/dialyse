package com.shuyah.dialyse

import android.content.Context
import android.os.Build
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

/**
 * VERROU DE L'APPLICATION par empreinte (ou visage, ou à défaut le code / schéma du téléphone).
 *
 * Contrairement à d'autres applications du propriétaire, il est OBLIGATOIRE ici : les alertes concernent la santé de patients. Si le téléphone n'a
 * aucun verrouillage d'écran, l'application refuse de s'ouvrir (elle dit pourquoi).
 *
 * Pour un développeur WinDev : une « authentification forte » du système, appelée par une procédure avec deux rappels (succès / échec).
 */
object Verrou {
    /** Moyens acceptés : biométrie, ou à défaut le code / schéma du téléphone. */
    private fun moyens(): Int =
        if (Build.VERSION.SDK_INT >= 30) BiometricManager.Authenticators.BIOMETRIC_STRONG or BiometricManager.Authenticators.DEVICE_CREDENTIAL
        else BiometricManager.Authenticators.BIOMETRIC_WEAK or BiometricManager.Authenticators.DEVICE_CREDENTIAL

    /** Vrai si le téléphone a une empreinte enregistrée ou un verrouillage d'écran. */
    fun disponible(c: Context): Boolean = BiometricManager.from(c).canAuthenticate(moyens()) == BiometricManager.BIOMETRIC_SUCCESS

    /** Affiche l'invite du téléphone ; `surOk` si l'utilisateur est reconnu, `surEchec(message)` s'il annule ou échoue. */
    fun verifier(a: FragmentActivity, titre: String, sousTitre: String, surOk: () -> Unit, surEchec: (String) -> Unit) {
        val invite = BiometricPrompt(a, ContextCompat.getMainExecutor(a), object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(resultat: BiometricPrompt.AuthenticationResult) = surOk()
            override fun onAuthenticationError(code: Int, message: CharSequence) = surEchec(message.toString())
        })
        invite.authenticate(BiometricPrompt.PromptInfo.Builder().setTitle(titre).setSubtitle(sousTitre).setAllowedAuthenticators(moyens()).build())
    }
}
