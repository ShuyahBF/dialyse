// CLÉS D'ACCÈS (WebAuthn) côté navigateur : conversion des formats et appels à l'authentificateur de l'appareil.
// Pour un développeur WinDev : le navigateur échange des identifiants en « base64url » ; ces fonctions font la traduction dans les deux sens.

/** Vrai si ce navigateur sait créer et utiliser des clés d'accès. */
export const clesAccesDisponibles = () => typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials;

const versOctets = (b64url) => {
  const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (b64url.length % 4)) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
};
const versBase64url = (tampon) => btoa(String.fromCharCode(...new Uint8Array(tampon))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

/** Options du serveur (texte) → options du navigateur (octets). */
function optionsCreation(o) {
  return { ...o, challenge: versOctets(o.challenge), user: { ...o.user, id: versOctets(o.user.id) },
    excludeCredentials: (o.excludeCredentials || []).map((c) => ({ ...c, id: versOctets(c.id) })) };
}
function optionsConnexion(o) {
  return { ...o, challenge: versOctets(o.challenge), allowCredentials: (o.allowCredentials || []).map((c) => ({ ...c, id: versOctets(c.id) })) };
}

/** Message lisible pour une erreur de l'authentificateur (annulation, aucune clé, appareil non compatible…). */
export function messageCleAcces(err) {
  if (err?.name === "NotAllowedError") return "Opération annulée ou expirée : réessayez et validez avec votre empreinte, votre visage ou le code du téléphone.";
  if (err?.name === "InvalidStateError") return "Ce téléphone ou cet ordinateur a déjà une clé d'accès pour votre compte.";
  if (err?.name === "NotSupportedError" || err?.name === "SecurityError") return "Les clés d'accès ne sont pas disponibles ici (navigateur ou adresse du site non compatible).";
  return null;
}

/** Crée une clé d'accès (le téléphone demande l'empreinte, le visage ou son code) ; rend la réponse à envoyer au serveur. */
export async function creerCleAcces(optionsServeur) {
  const c = await navigator.credentials.create({ publicKey: optionsCreation(optionsServeur) });
  return { id: c.id, rawId: versBase64url(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults?.() || {},
    response: { clientDataJSON: versBase64url(c.response.clientDataJSON), attestationObject: versBase64url(c.response.attestationObject), transports: c.response.getTransports?.() || [] } };
}

/** Utilise une clé d'accès pour se connecter ; rend la réponse à envoyer au serveur. */
export async function signerAvecCleAcces(optionsServeur) {
  const c = await navigator.credentials.get({ publicKey: optionsConnexion(optionsServeur) });
  return { id: c.id, rawId: versBase64url(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults?.() || {},
    response: { clientDataJSON: versBase64url(c.response.clientDataJSON), authenticatorData: versBase64url(c.response.authenticatorData),
      signature: versBase64url(c.response.signature), userHandle: c.response.userHandle ? versBase64url(c.response.userHandle) : null } };
}
