// Règles du mot de passe (les MÊMES que le serveur : `securite.mot_de_passe_assez_fort`) : 8 caractères au moins, avec une lettre et un chiffre.
// Utilisées pour avertir PENDANT la saisie, sans attendre l'enregistrement.

/** Liste des critères et de leur état : [{ id, libelle, ok }]. */
export function criteresMotDePasse(mdp) {
  const v = String(mdp || "");
  return [
    { id: "longueur", libelle: "8 caractères au moins", ok: v.length >= 8 },
    { id: "lettre", libelle: "Une lettre", ok: /[A-Za-zÀ-ÿ]/.test(v) },
    { id: "chiffre", libelle: "Un chiffre", ok: /\d/.test(v) },
  ];
}

/** Vrai si le mot de passe respecte tous les critères. */
export const motDePasseAssezFort = (mdp) => criteresMotDePasse(mdp).every((c) => c.ok);
