// Fiche de présentation d'un centre (formulaire commun) : responsable, adresse, coordonnées, IFU / RCCM, géolocalisation (position du téléphone ou saisie,
// lien vers la carte) et logo (aperçu, choix d'une image, retrait). Utilisée par « Centres De Dialyse » (super administrateur) et « Fiche Du Centre » (administrateur).
import { Image as IconeImage, LocateFixed, MapPin, Trash2, Upload } from "lucide-react";
import { useRef } from "react";
import Bouton from "./Bouton.jsx";
import { Texte } from "./Champs.jsx";
import { useApp } from "../lib/contexte.jsx";

const TAILLE_MAX = 600 * 1024;     // le serveur refuse au-delà de 600 Ko

/** Lit un fichier image en « data URL » (base64) ; le serveur vérifie et réduit réellement l'image. */
function lireImage(fichier) {
  return new Promise((ok, ko) => {
    const l = new FileReader();
    l.onload = () => ok(l.result);
    l.onerror = () => ko(new Error("Image illisible"));
    l.readAsDataURL(fichier);
  });
}

export default function FicheCentre({ form, maj, ligneWa = false, variableWa = "", clePresente = false }) {
  const { toast } = useApp();
  const fichier = useRef(null);

  async function choisirLogo(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!/^image\/(png|jpeg|webp)$/.test(f.type)) return toast("Logo : image PNG, JPEG ou WebP", "erreur");
    if (f.size > TAILLE_MAX) return toast("Logo trop lourd : 600 Ko au plus", "erreur");
    maj("logo", await lireImage(f));
  }

  // Position de l'appareil (le navigateur demande l'accord de la personne)
  function maPosition() {
    if (!navigator.geolocation) return toast("Géolocalisation indisponible sur cet appareil", "erreur");
    const id = toast("Recherche de la position en cours…", "attente");
    navigator.geolocation.getCurrentPosition(
      (p) => { maj("latitude", Number(p.coords.latitude.toFixed(6))); maj("longitude", Number(p.coords.longitude.toFixed(6))); toast("Position relevée : vérifiez puis enregistrez", "ok"); },
      () => toast("Position refusée ou introuvable : saisissez les coordonnées à la main", "erreur"),
      { enableHighAccuracy: true, timeout: 15000 });
    return id;
  }
  const aPosition = form.latitude !== "" && form.latitude != null && form.longitude !== "" && form.longitude != null;

  return (
    <div>
      {/* Logo */}
      <div className="mb-3 flex items-center gap-3 rounded-xl bg-brume p-3">
        <div className="flex h-16 w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-white ring-1 ring-encre/10">
          {form.logo ? <img src={form.logo} alt="Logo du centre" className="max-h-full max-w-full object-contain" /> : <IconeImage size={28} className="text-slate-400" aria-hidden="true" />}
        </div>
        <div className="flex flex-wrap gap-2">
          <Bouton petit icone={Upload} onClick={() => fichier.current?.click()}>{form.logo ? "Changer le logo" : "Ajouter le logo"}</Bouton>
          {form.logo && <Bouton petit variante="rouge" icone={Trash2} onClick={() => maj("logo", "")}>Retirer</Bouton>}
          <input ref={fichier} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={choisirLogo} />
          <p className="w-full text-xs text-slate-500">PNG, JPEG ou WebP, 600 Ko au plus. Il figure sur les factures, les rapports et le papier à en-tête.</p>
        </div>
      </div>
      <Texte libelle="Nom du responsable" valeur={form.responsable} onChange={(v) => maj("responsable", v)} placeholder="OUEDRAOGO Awa" />
      <Texte libelle="Fonction du responsable" valeur={form.titre_responsable} onChange={(v) => maj("titre_responsable", v)} placeholder="Directrice" />
      <Texte libelle="Adresse" valeur={form.adresse} onChange={(v) => maj("adresse", v)} placeholder="Secteur 15, avenue de la Nation" />
      <Texte libelle="Ville" valeur={form.ville} onChange={(v) => maj("ville", v)} placeholder="Ouagadougou" />
      <Texte libelle="Téléphone" valeur={form.telephone} onChange={(v) => maj("telephone", v)} placeholder="25 30 00 00" />
      <Texte libelle="E-mail" valeur={form.email} onChange={(v) => maj("email", v)} placeholder="awa.badini@gmail.com" type="email" />
      <Texte libelle="IFU / RCCM" valeur={form.identifiant_fiscal} onChange={(v) => maj("identifiant_fiscal", v)} placeholder="00012345 X" />
      {/* Ligne WhatsApp DÉDIÉE du centre (super administrateur) : émetteur créé dans SAWALI avec sa ligne privée ; la clé se saisit dans Render, jamais ici */}
      {ligneWa && (
        <div className="mb-3 rounded-xl bg-brume p-3">
          <p className="mb-2 text-xs font-semibold tracking-wide text-ardoise">Ligne WhatsApp du centre</p>
          <Texte libelle="Émetteur SAWALI de ce centre" valeur={form.wa_emetteur} onChange={(v) => maj("wa_emetteur", v.toLowerCase())} placeholder="dialyse-cmc" aide="Code de l'émetteur créé dans SAWALI et relié à la ligne privée du centre. Vide = ligne partagée « dialyse »." />
          {form.wa_emetteur && <p className={`mb-2 text-xs font-semibold ${clePresente ? "text-emerald-700" : "text-orange-700"}`}>{clePresente ? "✓ Clé reçue par le serveur : la ligne du centre est active." : `Clé absente : saisissez la variable ${variableWa} dans Render (service dialyse-api). Tant qu'elle manque, le centre utilise la ligne partagée.`}</p>}
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1 h-4 w-4 accent-emeraude" checked={!!form.wa_repli} onChange={(e) => maj("wa_repli", e.target.checked)} />
            En cas de panne de la ligne du centre, essayer la ligne partagée (le patient verra alors un autre numéro).</label>
        </div>
      )}
      {/* Géolocalisation */}
      <div className="mb-3 rounded-xl bg-brume p-3">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ardoise"><MapPin size={14} /> Géolocalisation</p>
        <div className="grid grid-cols-2 gap-2">
          <Texte libelle="Latitude" valeur={form.latitude ?? ""} onChange={(v) => maj("latitude", v)} placeholder="12.371400" inputMode="decimal" />
          <Texte libelle="Longitude" valeur={form.longitude ?? ""} onChange={(v) => maj("longitude", v)} placeholder="-1.519700" inputMode="decimal" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Bouton petit icone={LocateFixed} onClick={maPosition}>Utiliser ma position</Bouton>
          {aPosition && <a className="text-sm font-semibold text-emeraude underline" target="_blank" rel="noopener noreferrer"
            href={`https://www.openstreetmap.org/?mlat=${form.latitude}&mlon=${form.longitude}#map=17/${form.latitude}/${form.longitude}`}>Voir sur la carte</a>}
        </div>
        <p className="mt-1 text-xs text-slate-500">Placez-vous dans le centre pour relever la position. Elle figure en bas du papier à en-tête.</p>
      </div>
    </div>
  );
}

/** Corps envoyé au serveur : les coordonnées vides deviennent null (le serveur les efface). */
export function corpsFiche(form) {
  const { _wa, ...c } = form;                 // `_wa` : information d'affichage seulement, jamais envoyée
  for (const k of ["latitude", "longitude"]) if (c[k] === "" || c[k] === undefined) c[k] = null;
  return c;
}
