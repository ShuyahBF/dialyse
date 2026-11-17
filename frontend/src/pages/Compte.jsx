// Mon compte : changement de mot de passe (œil) et double authentification (activer / désactiver, avec code QR).
import { KeyRound, ShieldCheck, ShieldOff } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import ChampMotDePasse from "../composants/ChampMotDePasse.jsx";
import { Champ, Texte } from "../composants/Champs.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";

export default function Compte() {
  const { utilisateur, setUtilisateur, avecToast } = useApp();
  const [ancien, setAncien] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [prep, setPrep] = useState(null);           // { secret, uri, qr }
  const [code, setCode] = useState("");
  const [mdp2fa, setMdp2fa] = useState("");

  async function changerMdp() {
    await avecToast("Changement du mot de passe", () => api("/auth/changer-mot-de-passe", { methode: "POST", corps: { ancien, nouveau } }), () => "Mot de passe changé");
    setAncien(""); setNouveau(""); setUtilisateur({ ...utilisateur, doit_changer_mdp: false });
  }
  async function preparer() {
    const p = await avecToast("Préparation de la double authentification", () => api("/auth/2fa/preparer", { methode: "POST" }), () => "Scannez le code QR");
    setPrep({ ...p, qr: await QRCode.toDataURL(p.uri, { width: 200, margin: 1 }) });
  }
  async function activer() {
    await avecToast("Activation", () => api("/auth/2fa/activer", { methode: "POST", corps: { code } }), () => "Double authentification activée");
    setPrep(null); setCode(""); setUtilisateur({ ...utilisateur, totp_actif: true });
  }
  async function desactiver() {
    await avecToast("Désactivation", () => api("/auth/2fa/desactiver", { methode: "POST", corps: { mot_de_passe: mdp2fa, code } }), () => "Double authentification désactivée");
    setMdp2fa(""); setCode(""); setUtilisateur({ ...utilisateur, totp_actif: false });
  }
  const faible = nouveau.length < 8 || !/[a-zA-Z]/.test(nouveau) || !/\d/.test(nouveau);

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-semibold mb-1">Mon Compte</h1>
      <p className="text-sm text-slate-600 mb-4">{utilisateur.nom} · {utilisateur.role_libelle}</p>
      {utilisateur.doit_changer_mdp && <p className="mb-4 rounded-lg bg-orange-100 text-orange-900 px-3 py-2 text-sm">Votre mot de passe est provisoire : veuillez le changer maintenant.</p>}
      <section className="rounded-2xl bg-white p-4 border border-slate-200 mb-4">
        <h2 className="font-semibold mb-3 flex items-center gap-2"><KeyRound size={18} className="text-turquoise-600" /> Changer Mon Mot De Passe</h2>
        <Champ libelle="Mot de passe actuel"><ChampMotDePasse valeur={ancien} onChange={setAncien} /></Champ>
        <Champ libelle="Nouveau mot de passe" aide="8 caractères au moins, avec une lettre et un chiffre"><ChampMotDePasse valeur={nouveau} onChange={setNouveau} autoComplete="new-password" /></Champ>
        <Bouton icone={KeyRound} variante="principal" disabled={!ancien || faible} onClick={changerMdp}>Changer le mot de passe</Bouton>
      </section>
      <section className="rounded-2xl bg-white p-4 border border-slate-200 mb-4">
        <h2 className="font-semibold mb-2 flex items-center gap-2">
          {utilisateur.totp_actif ? <ShieldCheck size={18} className="text-emerald-600" /> : <ShieldOff size={18} className="text-slate-500" />} Double Authentification
        </h2>
        <p className="text-sm mb-3 text-slate-600">{utilisateur.totp_actif ? "Activée : un code de votre application d'authentification est demandé à chaque connexion." : "Désactivée. Conseillée pour les comptes qui voient des dossiers de patients."}</p>
        {!utilisateur.totp_actif && !prep && <Bouton icone={ShieldCheck} variante="vert" onClick={preparer}>Activer la double authentification</Bouton>}
        {prep && (
          <div>
            <img src={prep.qr} alt="Code QR à scanner" className="mx-auto mb-2" />
            <p className="text-xs text-slate-600 mb-2 text-center">Scannez avec votre application, ou saisissez la clé : <code className="font-mono">{prep.secret}</code></p>
            <Texte libelle="Code à 6 chiffres affiché par l'application" valeur={code} onChange={setCode} inputMode="numeric" placeholder="123456" />
            <Bouton icone={ShieldCheck} variante="vert" disabled={code.length < 6} onClick={activer}>Confirmer l'activation</Bouton>
          </div>
        )}
        {utilisateur.totp_actif && (
          <div>
            <Champ libelle="Mot de passe"><ChampMotDePasse valeur={mdp2fa} onChange={setMdp2fa} /></Champ>
            <Texte libelle="Code actuel de l'application" valeur={code} onChange={setCode} inputMode="numeric" placeholder="123456" />
            <Bouton icone={ShieldOff} variante="rouge" disabled={!mdp2fa || code.length < 6} onClick={desactiver}>Désactiver</Bouton>
          </div>
        )}
      </section>
      <BandeauVersion />
    </div>
  );
}
