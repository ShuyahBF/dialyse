// Pont entre le site Dialyse et l'application Android Dialyse (version hybride : le site est affiché dans une fenêtre intégrée qui expose
// l'objet « window.DialyseAndroid »). Dans un navigateur ordinaire cet objet n'existe pas : tout rend « indisponible » et le site reste identique.
// Pour un développeur WinDev : c'est l'équivalent d'un appel à une DLL du téléphone.

/** Vrai si le site est ouvert dans l'application Android Dialyse. */
export const dansApplication = () => typeof window !== "undefined" && !!window.DialyseAndroid;

/** Les notifications du téléphone sont-elles possibles (application récente) ? */
export const notificationsPossibles = () => { try { return dansApplication() && !!window.DialyseAndroid.notificationsActives; } catch { return false; } };

/** Les notifications sont-elles déjà activées sur ce téléphone ? */
export const notificationsActives = () => { try { return notificationsPossibles() && !!window.DialyseAndroid.notificationsActives(); } catch { return false; } };

/** Range le jeton de lecture et l'adresse du serveur dans l'application, qui interroge ensuite le serveur en arrière-plan. */
export function activerNotifications(adresseApi, jeton) {
  try { window.DialyseAndroid.notificationsActiver(adresseApi, jeton); return true; } catch { return false; }
}

/** Arrête les notifications de ce téléphone et oublie le jeton. */
export function desactiverNotifications() {
  try { window.DialyseAndroid.notificationsDesactiver(); } catch { /* sans importance */ }
}
