// Client de l'API : ajoute le jeton, transforme les erreurs en messages lisibles, déconnecte si la session a expiré.
const BASE = import.meta.env.VITE_API_URL || "";
let surSessionExpiree = () => {};
export const definirSurSessionExpiree = (f) => { surSessionExpiree = f; };

export const jeton = {
  lire: () => { try { return sessionStorage.getItem("jeton") || ""; } catch { return ""; } },
  ecrire: (v) => { try { v ? sessionStorage.setItem("jeton", v) : sessionStorage.removeItem("jeton"); } catch { /* stockage indisponible */ } },
};

/** Appel d'une route de l'API. Lève une Error dont le message est celui du serveur (en français). */
export async function api(chemin, { methode = "GET", corps, avecJeton = true } = {}) {
  const entetes = { "Content-Type": "application/json" };
  if (avecJeton && jeton.lire()) entetes.Authorization = "Bearer " + jeton.lire();
  let r;
  try {
    r = await fetch(BASE + chemin, { method: methode, headers: entetes, body: corps === undefined ? undefined : JSON.stringify(corps) });
  } catch {
    throw new Error("Serveur injoignable : vérifiez la connexion Internet");
  }
  let donnees = null;
  try { donnees = await r.json(); } catch { /* corps vide */ }
  if (!r.ok) {
    if (r.status === 401 && avecJeton && donnees?.detail !== "CODE_2FA_REQUIS") surSessionExpiree();
    const d = donnees?.detail;
    const message = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join(" ; ") : "Erreur " + r.status;
    const e = new Error(message);
    e.statut = r.status;
    throw e;
  }
  // Toutes les routes répondent en JSON : une réponse vide ou HTML signale un serveur mal configuré (jamais traité comme un succès silencieux).
  if (donnees === null) throw new Error("Réponse inattendue du serveur");
  return donnees;
}
