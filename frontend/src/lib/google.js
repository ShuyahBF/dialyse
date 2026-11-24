// google.js — connexion par compte Google, côté site Dialyse. Déroulé complet : backend/app/google_auth.py.
// Dans l'application Android, Google refuse sa page de connexion dans une fenêtre intégrée : on demande donc à l'application d'ouvrir le NAVIGATEUR du téléphone
// (pont « ouvrirNavigateur »), qui revient dans l'application par l'adresse « dialyse://google?code=… ».
import { api } from "./api.js";
import { dansApplication } from "./pontAndroid.js";

const BASE = import.meta.env.VITE_API_URL || "";

/** Le serveur est-il configuré pour Google ? (le bouton n'est affiché que si oui) */
export const googleDisponible = () => api("/auth/google/config", { avecJeton: false }).then((r) => !!r.disponible).catch(() => false);

/** « web » dans un navigateur, « app » dans l'application Android : le retour de Google n'est pas le même. */
export const cibleGoogle = () => (dansApplication() ? "app" : "web");

/** Adresse de départ de la connexion (le serveur renvoie ensuite vers Google). */
export const urlConnexionGoogle = () => `${BASE}/auth/google/demarrer?cible=${cibleGoogle()}`;

/** Ouvre une adresse Google : navigateur du téléphone dans l'application, même fenêtre sinon. Rend false si l'application est trop ancienne. */
export function ouvrirGoogle(url) {
  if (dansApplication()) {
    if (!window.DialyseAndroid.ouvrirNavigateur) return false;
    window.DialyseAndroid.ouvrirNavigateur(url);
    return true;
  }
  window.location.href = url;
  return true;
}

/** Messages clairs pour chaque cause d'échec renvoyée par le serveur (?erreur=…). */
export const MESSAGES_GOOGLE = {
  aucun_compte: "Aucun compte Dialyse n'est lié à ce compte Google. Connectez-vous avec votre identifiant, puis liez Google dans « Mon compte ».",
  deja_lie: "Ce compte Google est déjà lié à un autre compte Dialyse.",
  bloque: "Ce compte est désactivé : contactez l'administration.",
  refuse: "La connexion par Google a été annulée ou refusée.",
  google: "Google n'a pas pu confirmer votre identité (e-mail vérifié exigé). Réessayez.",
  etat: "Cette demande a expiré. Recommencez la connexion.",
};
