// Petites fonctions d'affichage (dates françaises, nombres, libellés de menu).

/** Date ISO AAAA-MM-JJ → JJ/MM/AAAA (vide si absente). */
export function dateFr(iso) {
  if (!iso) return "";
  const [a, m, j] = String(iso).slice(0, 10).split("-");
  return j && m && a ? `${j}/${m}/${a}` : iso;
}

/** Horodatage ISO → JJ/MM/AAAA HH:MM (heure locale). */
export function dateHeureFr(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

/** Aujourd'hui au format AAAA-MM-JJ (heure locale). */
export function aujourdhui() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Ajoute n jours à une date ISO. */
export function ajouterJours(iso, n) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Nombre avec virgule décimale française (vide si absent). */
export function nb(v, decimales = 1) {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toLocaleString("fr-FR", { maximumFractionDigits: decimales });
}

/** Règle 18 : chaque mot d'un libellé de menu commence par une majuscule (sigles conservés ; mot après apostrophe inchangé). */
export function titreMenu(libelle) {
  return String(libelle).split(" ").map((mot) => (mot ? mot[0].toUpperCase() + mot.slice(1) : mot)).join(" ");
}

/** Texte « Version X · déployée le JJ/MM/AAAA HH:MM » (court) ou complet avec lot et commit (pages d'administration). */
export function libelleVersion(v, detaille = false) {
  if (!v) return "";
  const commit = typeof __COMMIT__ !== "undefined" ? __COMMIT__ : "";
  const base = detaille ? `Version ${v.version} · Lot ${v.lot}${commit ? " · " + commit : ""}` : `Version ${v.version}`;
  return `${base} · déployée le ${v.deploye_le}`;
}

/** Montant en FCFA avec séparateur de milliers : 12345 → « 12 345 FCFA ». */
export function fcfa(v) {
  if (v === null || v === undefined || v === "") return "";
  return Math.round(Number(v)).toLocaleString("fr-FR").replace(/[\u202f\u00a0]/g, " ") + " FCFA";
}
