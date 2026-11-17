// Champs de formulaire communs : étiquette + saisie, liste déroulante (listes finies : règle 10), case à cocher.
export const classeChamp = "w-full rounded-lg border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-turquoise-500 bg-white";

export function Champ({ libelle, children, aide }) {
  return (
    <label className="block mb-3">
      <span className="block text-sm font-medium text-slate-700 mb-1">{libelle}</span>
      {children}
      {aide && <span className="block text-xs text-slate-500 mt-1">{aide}</span>}
    </label>
  );
}

export function Texte({ libelle, valeur, onChange, type = "text", placeholder, aide, ...autres }) {
  return (
    <Champ libelle={libelle} aide={aide}>
      <input type={type} value={valeur ?? ""} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className={classeChamp} {...autres} />
    </Champ>
  );
}

/** Liste déroulante. `options` : tableau de chaînes ou de {valeur, libelle}. Une valeur déjà enregistrée absente de la liste reste sélectionnable. */
export function Liste({ libelle, valeur, onChange, options, vide = "— Choisir —", aide }) {
  const opts = options.map((o) => (typeof o === "string" ? { valeur: o, libelle: o } : o));
  const inconnue = valeur && !opts.some((o) => o.valeur === valeur);
  return (
    <Champ libelle={libelle} aide={aide}>
      <select value={valeur ?? ""} onChange={(e) => onChange(e.target.value)} className={classeChamp}>
        <option value="">{vide}</option>
        {inconnue && <option value={valeur}>{valeur}</option>}
        {opts.map((o) => <option key={o.valeur} value={o.valeur}>{o.libelle}</option>)}
      </select>
    </Champ>
  );
}

export function Case({ libelle, valeur, onChange }) {
  return (
    <label className="flex items-center gap-2 mb-3 cursor-pointer">
      <input type="checkbox" checked={!!valeur} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 accent-turquoise-600" />
      <span className="text-sm">{libelle}</span>
    </label>
  );
}

/** Pastille d'état : couleur + texte (jamais la couleur seule : règle 16). */
export function Pastille({ couleur = "gris", children, icone: Icone }) {
  const c = { vert: "bg-emerald-100 text-emerald-800", rouge: "bg-rose-100 text-rose-800", orange: "bg-orange-100 text-orange-800",
              bleu: "bg-sky-100 text-sky-800", gris: "bg-slate-100 text-slate-700", violet: "bg-violet-100 text-violet-800" }[couleur];
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${c}`}>{Icone && <Icone size={13} />}{children}</span>;
}
