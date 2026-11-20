// « Apparence De L'Accueil » (super administrateur) : image ou vidéo de fond de la page de connexion, avec aperçu, assombrissement réglable et retrait.
// Règle 15 : chaque action a son pictogramme ; un réglage n'est JAMAIS enregistré « en silence » (bouton Enregistrer actif seulement si modifié).
// Sécurité : le serveur lit le vrai contenu du fichier (SVG et formats actifs refusés), réduit les images (1920 px) et limite les vidéos (12 Mo).
import { ImageIcon, RefreshCw, Save, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import FondAccueil from "../composants/FondAccueil.jsx";
import { api, envoyerBinaire } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";

const FORMATS = "image/png,image/jpeg,image/webp,video/mp4,video/webm";

export default function FondAccueilPage() {
  const { avecToast, toast } = useApp();
  const [fond, setFond] = useState(null);                 // fond enregistré sur le serveur
  const [voile, setVoile] = useState(45);                 // assombrissement en cours de réglage
  const entree = useRef(null);
  const charger = useCallback(async () => { const f = await api("/fond-accueil", { avecJeton: false }); setFond(f); setVoile(f.voile); return f; }, []);
  useEffect(() => { charger().catch((e) => toast(e.message, "erreur")); }, [charger, toast]);
  if (!fond) return <div className="flex justify-center py-10"><span className="jauge" /></div>;

  const modifie = fond.actif && voile !== fond.voile;
  async function choisir(e) {
    const fichier = e.target.files?.[0];
    e.target.value = "";                                  // permet de rechoisir le même fichier
    if (!fichier) return;
    if (fichier.size > 12 * 1024 * 1024) { toast("Fichier trop lourd : image 8 Mo au plus, vidéo 12 Mo au plus", "erreur"); return; }
    await avecToast("Envoi du fond", async () => envoyerBinaire("/fond-accueil/media", await fichier.arrayBuffer(), "PUT"), (f) => (f.type === "video" ? "Vidéo de fond enregistrée" : "Image de fond enregistrée"));
    await charger();
  }
  const enregistrer = async () => { await avecToast("Enregistrement du réglage", () => api("/fond-accueil/reglages", { methode: "PUT", corps: { voile } }), () => "Assombrissement enregistré"); await charger(); };
  const retirer = async () => {
    if (!window.confirm("Retirer le fond de la page d'accueil ? Le fond bleu nuit habituel sera rétabli.")) return;
    await avecToast("Retrait du fond", () => api("/fond-accueil", { methode: "DELETE" }), () => "Fond retiré");
    await charger();
  };
  const actualiser = () => avecToast("Actualisation", charger, (f) => (f.actif ? `Fond actuel : ${f.type === "video" ? "vidéo" : "image"} (${Math.round(f.taille / 1024)} Ko)` : "Aucun fond défini"));

  return (
    <div className="max-w-3xl">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-editorial text-2xl font-bold italic text-encre">Apparence de l'accueil</h1>
        <Bouton icone={RefreshCw} petit onClick={actualiser}>Actualiser</Bouton>
      </div>
      <BandeauVersion detaille className="mb-4" />
      <p className="mb-4 text-sm text-ardoise">Image ou vidéo de fond de la page de connexion, la même pour tous les centres. Une vidéo est lue sans son et en boucle.</p>

      {/* Aperçu : même rendu que la page de connexion (carte blanche posée sur le fond, voile compris) */}
      <div className="relative mb-4 grid h-64 place-items-center overflow-hidden rounded-2xl bg-encre ring-1 ring-encre/10">
        {fond.actif && <FondAccueil fond={{ ...fond, voile }} className="absolute inset-0" />}
        <div className="relative w-48 rounded-2xl bg-white p-4 text-center shadow-xl">
          <p className="font-editorial text-sm font-bold italic text-encre">Gestion des actes de dialyse</p>
          <div className="mt-2 h-2 rounded bg-slate-200" /><div className="mt-1.5 h-2 rounded bg-slate-200" /><div className="mt-3 h-5 rounded-full bg-emeraude" />
        </div>
        {!fond.actif && <p className="absolute bottom-2 text-xs text-white/70">Aucun fond défini : fond bleu nuit habituel</p>}
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <input ref={entree} type="file" accept={FORMATS} className="hidden" onChange={choisir} data-testid="fichier-fond" />
        <Bouton variante="principal" icone={fond.actif ? Upload : ImageIcon} onClick={() => entree.current?.click()}>{fond.actif ? "Remplacer le fond" : "Choisir une image ou une vidéo"}</Bouton>
        {fond.actif && <Bouton variante="rouge" icone={Trash2} onClick={retirer}>Retirer le fond</Bouton>}
      </div>

      {fond.actif && (
        <div className="rounded-2xl bg-white p-4 ring-1 ring-encre/5">
          <label className="block text-sm font-semibold text-encre" htmlFor="voile">Assombrissement du fond : <b className="tabular-nums text-citron-600">{voile} %</b></label>
          <p className="mb-2 text-xs text-ardoise">Plus il est élevé, plus la carte de connexion est lisible sur une image claire.</p>
          <input id="voile" type="range" min="0" max="80" step="5" value={voile} onChange={(e) => setVoile(Number(e.target.value))} className="w-full accent-emeraude" />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Bouton icone={Save} variante="vert" disabled={!modifie} onClick={enregistrer}>Enregistrer</Bouton>
            {modifie && <span className="text-sm font-semibold text-orange-700">modifié, non enregistré</span>}
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-ardoise">Formats : PNG, JPEG, WebP (8 Mo au plus, réduite à 1920 px) ou MP4, WebM (12 Mo au plus). Préférez une vidéo courte et légère : elle se charge avant la connexion.</p>
    </div>
  );
}
