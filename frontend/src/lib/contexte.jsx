// Contexte global : utilisateur connecté, version du serveur, toasts (« … en cours » puis résultat) et attente longue.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, centre as centreStock, definirSurSessionExpiree, jeton } from "./api.js";

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

export function Fournisseur({ children }) {
  const [utilisateur, setUtilisateur] = useState(null);
  const [pret, setPret] = useState(false);
  const [version, setVersion] = useState(null);
  const [toasts, setToasts] = useState([]);
  // Multi-centres : liste des centres visibles et centre de travail choisi (comptes du groupe seulement ; les autres ont le leur, imposé par le serveur).
  const [centres, setCentres] = useState([]);
  const [centreChoisi, setCentreChoisi] = useState(centreStock.lire());
  const choisirCentre = useCallback((id) => { centreStock.ecrire(id || ""); setCentreChoisi(id || ""); }, []);

  /** Affiche un toast (type : info | ok | erreur | attente). Retourne son identifiant ; les toasts « attente » restent jusqu'à retrait. */
  const toast = useCallback((message, type = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, message, type }].slice(-3));      // 3 toasts visibles au plus
    if (type !== "attente") setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), type === "erreur" ? 7000 : 3500);
    return id;
  }, []);
  const retirer = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  /**
   * Exécute une action asynchrone avec toast « enMessage… en cours » puis toast de résultat (règle 17 : jamais d'actualisation silencieuse).
   * `resultat(valeur)` renvoie le texte du toast de succès.
   */
  const avecToast = useCallback(async (enCours, action, resultat) => {
    const id = toast(enCours + " en cours…", "attente");
    try {
      const v = await action();
      retirer(id);
      toast(resultat ? resultat(v) : "Terminé", "ok");
      return v;
    } catch (e) {
      retirer(id);
      toast(e.message, "erreur");
      throw e;
    }
  }, [toast, retirer]);

  const deconnecter = useCallback(() => { jeton.ecrire(""); centreStock.ecrire(""); setCentreChoisi(""); setCentres([]); setUtilisateur(null); }, []);

  // Après connexion : liste des centres ; un compte du groupe sans choix reprend le sien, ou celui du seul centre existant.
  useEffect(() => {
    if (!utilisateur) return;
    api("/centres").then((l) => {
      setCentres(l);
      if (utilisateur.groupe && !l.some((c) => c.id === centreStock.lire())) choisirCentre(l.length === 1 ? l[0].id : "");
    }).catch(() => {});
  }, [utilisateur, choisirCentre]);

  useEffect(() => {
    definirSurSessionExpiree(() => { deconnecter(); toast("Session expirée, reconnectez-vous", "erreur"); });
    api("/api/version", { avecJeton: false }).then(setVersion).catch(() => {});
    if (jeton.lire()) api("/me").then(setUtilisateur).catch(() => jeton.ecrire("")).finally(() => setPret(true));
    else setPret(true);
  }, [deconnecter, toast]);

  const rechargerCentres = useCallback(() => api("/centres").then(setCentres), []);
  const valeur = useMemo(() => ({ utilisateur, setUtilisateur, pret, version, toast, retirer, avecToast, deconnecter, toasts, centres, centreChoisi, choisirCentre, rechargerCentres }),
    [utilisateur, pret, version, toast, retirer, avecToast, deconnecter, toasts, centres, centreChoisi, choisirCentre, rechargerCentres]);
  return <Ctx.Provider value={valeur}>{children}</Ctx.Provider>;
}
