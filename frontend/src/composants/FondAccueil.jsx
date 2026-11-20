// Fond de la page d'accueil (connexion) : image ou vidéo choisie par le super administrateur, avec un voile sombre réglable pour garder la carte lisible.
// Sans fond (ou si la lecture échoue) : le fond bleu nuit habituel. La vidéo est muette, en boucle, et n'est PAS lue si la personne a demandé moins d'animations.
import { useEffect, useState } from "react";
import { api, urlApi } from "../lib/api.js";

/** Lit la description publique du fond (aucune connexion exigée). */
export function useFondAccueil() {
  const [fond, setFond] = useState(null);
  useEffect(() => { api("/fond-accueil", { avecJeton: false }).then(setFond).catch(() => setFond(null)); }, []);
  return [fond, setFond];
}

/** Dessine le fond (positionné derrière tout le contenu de la page qui le contient). `fond` = réponse de GET /fond-accueil. */
export default function FondAccueil({ fond, className = "fixed inset-0" }) {
  if (!fond?.actif) return null;
  const adresse = urlApi(`/fond-accueil/media?v=${fond.version}`);
  const reduit = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return (
    <div className={`${className} -z-0 overflow-hidden`} aria-hidden="true">
      {fond.type === "image" && <img src={adresse} alt="" className="h-full w-full object-cover" />}
      {fond.type === "video" && !reduit && <video src={adresse} className="h-full w-full object-cover" autoPlay muted loop playsInline preload="auto" disablePictureInPicture />}
      <div className="absolute inset-0 bg-encre" style={{ opacity: (fond.voile ?? 45) / 100 }} />
    </div>
  );
}
