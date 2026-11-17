// Tri des tableaux (règle 19) : 1er clic croissant ▲, 2e décroissant ▼, 3e ordre d'origine. Les valeurs vides restent TOUJOURS en dernier.
import { useState } from "react";

/** Texte comparable : minuscules sans accents. */
export const sansAccent = (t) => String(t ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const vide = (v) => v === null || v === undefined || v === "" || (typeof v === "number" && Number.isNaN(v));

/** Compare deux valeurs : nombres numériquement, dates ISO chronologiquement (texte AAAA-MM-JJ), textes sans accents ni casse. */
export function comparer(a, b) {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return sansAccent(a).localeCompare(sansAccent(b), "fr", { numeric: true });
}

/**
 * Trie une copie de `lignes` selon la colonne `cle` (lecture par `lecteurs[cle]` ou `ligne[cle]`) et le sens (1, -1 ou 0 = ordre d'origine).
 */
export function trierLignes(lignes, cle, sens, lecteurs = {}) {
  if (!cle || !sens) return lignes;
  const lire = (l) => (lecteurs[cle] ? lecteurs[cle](l) : l[cle]);
  return [...lignes].sort((x, y) => {
    const a = lire(x), b = lire(y);
    if (vide(a) && vide(b)) return 0;
    if (vide(a)) return 1;            // vide toujours en dernier, quel que soit le sens
    if (vide(b)) return -1;
    return sens * comparer(a, b);
  });
}

/** Crochet React : état du tri et fonction de bascule (croissant → décroissant → origine). */
export function useTri() {
  const [etat, setEtat] = useState({ cle: "", sens: 0 });
  const basculer = (cle) => setEtat((e) => (e.cle !== cle ? { cle, sens: 1 } : e.sens === 1 ? { cle, sens: -1 } : { cle: "", sens: 0 }));
  return { ...etat, basculer };
}
