// Mon compte : changement de mot de passe (œil) et double authentification (activer / désactiver, avec code QR).
import { Fingerprint, KeyRound, MessageCircle, ShieldCheck, ShieldOff, Trash2 } from "lucide-react";
import QRCode from "qrcode";
import { useCallback, useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import ChampMotDePasse from "../composants/ChampMotDePasse.jsx";
import ForceMotDePasse from "../composants/ForceMotDePasse.jsx";
import { Champ, Texte } from "../composants/Champs.jsx";
import { api } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { dateHeureFr } from "../lib/format.js";
import { motDePasseAssezFort } from "../lib/motdepasse.js";
import { clesAccesDisponibles, creerCleAcces, messageCleAcces } from "../lib/passkeys.js";

export default function Compte() {
  const { utilisateur, setUtilisateur, avecToast, toast } = useApp();
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
  // ---- WhatsApp et clés d'accès ----
  const [acces, setAcces] = useState(null);
  const [cles, setCles] = useState([]);
  const [tel, setTel] = useState("");
  const [codeTel, setCodeTel] = useState("");
  const [envoye, setEnvoye] = useState(false);
  const [mdpAcces, setMdpAcces] = useState("");
  const [nomCle, setNomCle] = useState("");
  const chargerAcces = useCallback(async () => { setAcces(await api("/compte/acces")); setCles((await api("/auth/passkey")).cles); }, []);
  useEffect(() => { chargerAcces().catch(() => {}); }, [chargerAcces]);
  async function envoyerCodeTel() { await avecToast("Envoi du code WhatsApp", () => api("/compte/telephone/demande", { methode: "POST", corps: { telephone: tel } }), () => "Code envoyé par WhatsApp"); setEnvoye(true); }
  async function verifierTel() { await avecToast("Vérification du numéro", () => api("/compte/telephone/verifier", { methode: "POST", corps: { code: codeTel } }), (r) => `Numéro ${r.telephone} vérifié`); setEnvoye(false); setTel(""); setCodeTel(""); await chargerAcces(); }
  async function retirerTel() { await avecToast("Retrait du numéro", () => api("/compte/telephone", { methode: "DELETE" }), () => "Numéro retiré"); await chargerAcces(); }
  async function basculerOtpWa() {
    await avecToast("Enregistrement", () => api("/compte/otp-wa", { methode: "PUT", corps: { actif: !acces.otp_wa_actif, mot_de_passe: mdpAcces } }), (r) => (r.otp_wa_actif ? "Code WhatsApp exigé à chaque connexion" : "Code WhatsApp non exigé"));
    setMdpAcces(""); await chargerAcces();
  }
  async function ajouterCle() {
    try {
      const o = await avecToast("Préparation de la clé d'accès", () => api("/auth/passkey/options-enregistrement", { methode: "POST", corps: { mot_de_passe: mdpAcces } }), () => "Validez avec votre empreinte, votre visage ou le code de l'appareil");
      const credential = await creerCleAcces(o.options);
      await avecToast("Enregistrement de la clé", () => api("/auth/passkey/enregistrer", { methode: "POST", corps: { defi_id: o.defi_id, credential, nom: nomCle } }), (r) => `Clé « ${r.nom} » ajoutée`);
      setMdpAcces(""); setNomCle(""); await chargerAcces();
    } catch (e) { const m = messageCleAcces(e); if (m) toast(m, "erreur"); }
  }
  async function supprimerCle(c) { await avecToast("Suppression de la clé", () => api(`/auth/passkey/${c.credential_id}/supprimer`, { methode: "POST", corps: { mot_de_passe: mdpAcces } }), () => "Clé supprimée"); setMdpAcces(""); await chargerAcces(); }
  const faible = !motDePasseAssezFort(nouveau);

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-semibold mb-1">Mon Compte</h1>
      <p className="text-sm text-slate-600 mb-4">{utilisateur.nom} · {utilisateur.role_libelle}</p>
      {utilisateur.doit_changer_mdp && <p className="mb-4 rounded-lg bg-orange-100 text-orange-900 px-3 py-2 text-sm">Votre mot de passe est provisoire : veuillez le changer maintenant.</p>}
      <section className="rounded-2xl bg-white p-4 ring-1 ring-encre/10 mb-4">
        <h2 className="font-semibold mb-3 flex items-center gap-2"><KeyRound size={18} className="text-turquoise-600" /> Changer Mon Mot De Passe</h2>
        <Champ libelle="Mot de passe actuel"><ChampMotDePasse valeur={ancien} onChange={setAncien} /></Champ>
        <Champ libelle="Nouveau mot de passe" aide="8 caractères au moins, avec une lettre et un chiffre"><ChampMotDePasse valeur={nouveau} onChange={setNouveau} autoComplete="new-password" /></Champ>
        <ForceMotDePasse valeur={nouveau} />
        <Bouton icone={KeyRound} variante="principal" disabled={!ancien || faible} onClick={changerMdp}>Changer le mot de passe</Bouton>
      </section>
      <section className="rounded-2xl bg-white p-4 ring-1 ring-encre/10 mb-4">
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
      {acces && (
        <section className="rounded-2xl bg-white p-4 ring-1 ring-encre/10 mb-4">
          <h2 className="font-semibold mb-2 flex items-center gap-2"><MessageCircle size={18} className="text-emerald-600" /> Numéro WhatsApp</h2>
          {!acces.whatsapp_disponible && <p className="text-sm text-slate-500">WhatsApp (Liluvine) n'est pas encore activé sur le serveur : la clé LILUVINE_WA_HMAC reste à saisir dans Render.</p>}
          {acces.whatsapp_disponible && (acces.telephone_verifie ? (
            <div>
              <p className="text-sm mb-2">Numéro vérifié : <b>{acces.telephone}</b>. Il permet la connexion par code WhatsApp et le lien « mot de passe oublié ».</p>
              <Champ libelle="Mot de passe (pour modifier le second facteur)"><ChampMotDePasse valeur={mdpAcces} onChange={setMdpAcces} /></Champ>
              <div className="flex flex-wrap gap-2">
                <Bouton icone={acces.otp_wa_actif ? ShieldOff : ShieldCheck} variante={acces.otp_wa_actif ? "rouge" : "vert"} disabled={!mdpAcces} onClick={basculerOtpWa}>
                  {acces.otp_wa_actif ? "Ne plus exiger le code WhatsApp à la connexion" : "Exiger un code WhatsApp à chaque connexion"}</Bouton>
                <Bouton icone={Trash2} onClick={retirerTel}>Retirer ce numéro</Bouton>
              </div>
            </div>
          ) : (
            <div>
              <Texte libelle="Votre numéro WhatsApp" valeur={tel} onChange={setTel} inputMode="tel" placeholder="+226 70 12 34 56" aide="Un code de vérification vous est envoyé sur ce numéro." />
              {envoye && <Texte libelle="Code reçu par WhatsApp (6 chiffres)" valeur={codeTel} onChange={setCodeTel} inputMode="numeric" placeholder="123456" />}
              <div className="flex gap-2">
                <Bouton icone={MessageCircle} variante="vert" disabled={!tel} onClick={envoyerCodeTel}>{envoye ? "Renvoyer le code" : "Recevoir un code"}</Bouton>
                {envoye && <Bouton icone={ShieldCheck} variante="principal" disabled={codeTel.length < 6} onClick={verifierTel}>Vérifier le numéro</Bouton>}
              </div>
            </div>
          ))}
        </section>
      )}
      {acces && clesAccesDisponibles() && (
        <section className="rounded-2xl bg-white p-4 ring-1 ring-encre/10 mb-4">
          <h2 className="font-semibold mb-2 flex items-center gap-2"><Fingerprint size={18} className="text-violet-600" /> Empreinte, visage ou code de l'appareil</h2>
          <p className="text-sm text-slate-600 mb-3">Connexion sans mot de passe avec une clé d'accès enregistrée sur cet appareil (rien de secret ne quitte l'appareil).</p>
          <ul className="space-y-1.5 mb-3">
            {cles.map((c) => (
              <li key={c.credential_id} className="flex items-center gap-2 rounded-lg ring-1 ring-encre/10 px-3 py-1.5 text-sm">
                <Fingerprint size={16} className="text-violet-600" /><span className="flex-1">{c.nom}<span className="block text-xs text-slate-500">{c.dernier_usage ? "utilisée le " + dateHeureFr(c.dernier_usage) : "jamais utilisée"}</span></span>
                <Bouton petit variante="neutre" icone={Trash2} disabled={!mdpAcces} onClick={() => supprimerCle(c)}>Supprimer</Bouton>
              </li>
            ))}
            {!cles.length && <li className="text-sm text-slate-500">Aucune clé d'accès enregistrée.</li>}
          </ul>
          <Champ libelle="Mot de passe (demandé pour ajouter ou supprimer une clé)"><ChampMotDePasse valeur={mdpAcces} onChange={setMdpAcces} /></Champ>
          <Texte libelle="Nom de cet appareil" valeur={nomCle} onChange={setNomCle} placeholder="Téléphone de BADINI Awa" />
          <Bouton icone={Fingerprint} variante="principal" disabled={!mdpAcces} onClick={ajouterCle}>Ajouter cet appareil</Bouton>
        </section>
      )}
      <BandeauVersion />
    </div>
  );
}
