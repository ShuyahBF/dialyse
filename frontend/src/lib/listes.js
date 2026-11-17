// Listes finies du serveur (listes déroulantes), lues une seule fois puis gardées en mémoire.
import { useEffect, useState } from "react";
import { api } from "./api.js";

let cache = null;
export function useListes() {
  const [l, setL] = useState(cache);
  useEffect(() => { if (!cache) api("/listes").then((x) => { cache = x; setL(x); }).catch(() => {}); }, []);
  return l || { sexes: [], groupes: [], statuts: [], causes: [], serologies: [], prises_en_charge: [], types_acces: [], anticoagulations: [], jours: [], creneaux: [] };
}

/** Formulaire avec détection des modifications (bouton Enregistrer actif seulement si changé : règle 15). */
export function useFormulaire(initial) {
  const [valeurs, setValeurs] = useState(initial);
  const [origine, setOrigine] = useState(initial);
  const maj = (cle, v) => setValeurs((x) => ({ ...x, [cle]: v }));
  const modifie = JSON.stringify(valeurs) !== JSON.stringify(origine);
  const reinitialiser = (nouveau) => { setValeurs(nouveau); setOrigine(nouveau); };
  return { valeurs, maj, setValeurs, modifie, reinitialiser };
}
