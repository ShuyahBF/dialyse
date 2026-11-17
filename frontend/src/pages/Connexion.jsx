// Page de connexion : carte centrée, état du serveur, version, œil sur le mot de passe.
// Moyens d'accès : mot de passe (+ code de l'application d'authentification ou de WhatsApp), code WhatsApp, clé d'accès (empreinte, visage), mot de passe oublié.
import { Fingerprint, KeyRound, LogIn, MessageCircle, ServerCog, ServerCrash } from "lucide-react";
import { useEffect, useState } from "react";
import BandeauVersion from "../composants/BandeauVersion.jsx";
import Bouton from "../composants/Bouton.jsx";
import ChampMotDePasse from "../composants/ChampMotDePasse.jsx";
import Logo from "../composants/Logo.jsx";
import { Champ, Texte } from "../composants/Champs.jsx";
import { api, jeton } from "../lib/api.js";
import { useApp } from "../lib/contexte.jsx";
import { clesAccesDisponibles, messageCleAcces, signerAvecCleAcces } from "../lib/passkeys.js";

export default function Connexion() {
  const { setUtilisateur, toast, retirer } = useApp();
  const [mode, setMode] = useState("mdp");                 // mdp | wa | oubli
  const [login, setLogin] = useState("");
  const [mdp, setMdp] = useState("");
  const [code, setCode] = useState("");
  const [code2, setCode2] = useState("");                  // code de l'application d'authentification (connexion par WhatsApp)
  const [telephone, setTelephone] = useState("");
  const [codeEnvoye, setCodeEnvoye] = useState(false);
  const [besoinCode, setBesoinCode] = useState("");        // "" | "totp" | "wa"
  const [attente, setAttente] = useState(false);
  const [etat, setEtat] = useState("verification");        // verification | actif | lent | injoignable
  const [options, setOptions] = useState({ whatsapp: false });

  // État du serveur : « Serveur actif », lent (> 3 s) ou injoignable ; moyens d'accès proposés.
  useEffect(() => {
    const debut = Date.now();
    api("/api/sante", { avecJeton: false })
      .then((s) => setEtat(s.base === "ok" ? (Date.now() - debut > 3000 ? "lent" : "actif") : "injoignable"))
      .catch(() => setEtat("injoignable"));
    api("/auth/options", { avecJeton: false }).then(setOptions).catch(() => {});
  }, []);

  /** Exécute une étape avec toast « Patientez… » et jauge ; remplace le texte d'erreur par le message du serveur. */
  async function etape(texte, action) {
    setAttente(true);
    const id = toast(`Patientez… ${texte}`, "attente");
    try { await action(); } catch (err) {
      if (err.message === "CODE_2FA_REQUIS") { setBesoinCode("totp"); toast("Saisissez le code de votre application d'authentification", "info"); }
      else if (err.message === "CODE_WA_REQUIS") { setBesoinCode("wa"); toast("Un code vous a été envoyé par WhatsApp", "info"); }
      else toast(err.message, "erreur");
    } finally { retirer(id); setAttente(false); }
  }
  const ouvrir = async (r) => { jeton.ecrire(r.jeton); setUtilisateur(await api("/me")); };

  const envoyerMdp = (e) => { e.preventDefault(); etape("connexion en cours", async () => ouvrir(await api("/auth/login", { methode: "POST", avecJeton: false, corps: { login, mot_de_passe: mdp, code_2fa: code } }))); };
  const demanderCodeWa = (e) => { e.preventDefault(); etape("envoi du code", async () => { await api("/auth/otp/demande", { methode: "POST", avecJeton: false, corps: { telephone } }); setCodeEnvoye(true); toast("Si ce numéro est enregistré, un code vient d'être envoyé", "ok"); }); };
  const verifierCodeWa = (e) => { e.preventDefault(); etape("vérification du code", async () => ouvrir(await api("/auth/otp/verifier", { methode: "POST", avecJeton: false, corps: { telephone, code, code_2fa: code2 } }))); };
  const oubli = (e) => { e.preventDefault(); etape("envoi du lien", async () => { const r = await api("/auth/oubli", { methode: "POST", avecJeton: false, corps: { identifiant: login } }); toast(r.message, "ok"); setMode("mdp"); }); };
  const cleAcces = () => etape("lecture de la clé d'accès", async () => {
    try {
      const o = await api("/auth/passkey/options-connexion", { methode: "POST", avecJeton: false });
      const credential = await signerAvecCleAcces(o.options);
      await ouvrir(await api("/auth/passkey/connexion", { methode: "POST", avecJeton: false, corps: { defi_id: o.defi_id, credential } }));
    } catch (err) { throw new Error(messageCleAcces(err) || err.message); }
  });

  const etats = {
    verification: { txt: "Vérification du serveur…", cl: "text-slate-500", Ic: ServerCog }, actif: { txt: "Serveur actif", cl: "text-emerald-700", Ic: ServerCog },
    lent: { txt: "Serveur lent à répondre", cl: "text-orange-700", Ic: ServerCog }, injoignable: { txt: "Serveur injoignable", cl: "text-rose-700", Ic: ServerCrash },
  }[etat];

  return (
    <div className="grid min-h-screen place-items-center bg-encre px-4 py-10">
      <main className="w-full max-w-sm rounded-3xl bg-white p-6 shadow-2xl sm:p-8">
        <div className="flex flex-col items-center">
          <Logo taille={40} />
          <h1 className="mt-5 text-center font-editorial text-2xl font-bold italic text-encre">Gestion des actes de dialyse</h1>
          <p className="mt-1 text-sm text-ardoise">Espace réservé au personnel de la clinique</p>
        </div>
        <div className="mt-5" />

        {mode === "mdp" && (
          <form onSubmit={envoyerMdp}>
            <Texte libelle="Identifiant" valeur={login} onChange={setLogin} autoComplete="username" placeholder="awa.badini" autoFocus />
            <Champ libelle="Mot de passe"><ChampMotDePasse valeur={mdp} onChange={setMdp} /></Champ>
            {besoinCode && <Texte libelle={besoinCode === "wa" ? "Code reçu par WhatsApp (6 chiffres)" : "Code de l'application d'authentification (6 chiffres)"} valeur={code} onChange={setCode} inputMode="numeric" autoComplete="one-time-code" placeholder="123456" />}
            <Bouton type="submit" variante="principal" icone={LogIn} attente={attente} className="w-full" disabled={!login || !mdp}>Se connecter</Bouton>
          </form>
        )}

        {mode === "wa" && (
          <form onSubmit={codeEnvoye ? verifierCodeWa : demanderCodeWa}>
            <Texte libelle="Numéro WhatsApp du compte" valeur={telephone} onChange={setTelephone} inputMode="tel" placeholder="+226 70 12 34 56" disabled={codeEnvoye} autoFocus />
            {codeEnvoye && <Texte libelle="Code reçu par WhatsApp (6 chiffres)" valeur={code} onChange={setCode} inputMode="numeric" autoComplete="one-time-code" placeholder="123456" autoFocus />}
            {besoinCode === "totp" && <Texte libelle="Code de l'application d'authentification (6 chiffres)" valeur={code2} onChange={setCode2} inputMode="numeric" placeholder="123456" />}
            <Bouton type="submit" variante="vert" icone={MessageCircle} attente={attente} className="w-full" disabled={!telephone || (codeEnvoye && !code)}>{codeEnvoye ? "Valider le code" : "Recevoir un code"}</Bouton>
          </form>
        )}

        {mode === "oubli" && (
          <form onSubmit={oubli}>
            <p className="text-sm text-slate-600 mb-3">Un lien pour choisir un nouveau mot de passe est envoyé sur le numéro WhatsApp vérifié du compte.</p>
            <Texte libelle="Identifiant ou numéro WhatsApp" valeur={login} onChange={setLogin} placeholder="awa.badini" autoFocus />
            <Bouton type="submit" variante="orange" icone={KeyRound} attente={attente} className="w-full" disabled={!login}>Envoyer le lien</Bouton>
          </form>
        )}

        <div className="mt-4 space-y-2">
          {clesAccesDisponibles() && mode === "mdp" && <Bouton icone={Fingerprint} className="w-full" disabled={attente} onClick={cleAcces}>Empreinte, visage ou code de l'appareil</Bouton>}
          {options.whatsapp && mode !== "wa" && <Bouton icone={MessageCircle} className="w-full" onClick={() => { setMode("wa"); setCodeEnvoye(false); setCode(""); }}>Se connecter par code WhatsApp</Bouton>}
          {options.whatsapp && mode === "mdp" && <button type="button" onClick={() => setMode("oubli")} className="block mx-auto text-sm text-turquoise-700 underline">Mot de passe oublié ?</button>}
          {mode !== "mdp" && <Bouton icone={LogIn} className="w-full" onClick={() => { setMode("mdp"); setCode(""); }}>Retour à la connexion par mot de passe</Bouton>}
        </div>
        <p className={`mt-4 flex items-center justify-center gap-1.5 text-sm ${etats.cl}`}><etats.Ic size={16} /> {etats.txt}</p>
        <BandeauVersion className="text-center mt-1" />
      </main>
    </div>
  );
}
