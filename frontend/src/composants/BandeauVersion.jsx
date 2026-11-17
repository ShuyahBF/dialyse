// Version et date de déploiement (règle 2) : libellé court partout, libellé complet (lot, commit) dans l'administration.
import { libelleVersion } from "../lib/format.js";
import { useApp } from "../lib/contexte.jsx";

export default function BandeauVersion({ detaille = false, className = "" }) {
  const { version } = useApp();
  if (!version) return null;
  return <p className={`text-xs text-slate-500 ${className}`}>{libelleVersion(version, detaille)}</p>;
}
