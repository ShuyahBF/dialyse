// Logo Dialyse (même présentation que ZandGo) : emblème rond blanc (goutte bleu marine traversée d'un tracé de pouls orange)
// + nom « Dia » / « lyse » (blanc et orange sur fond sombre, bleu marine et orange sur fond clair).
export function Embleme({ taille = 44 }) {
  return (
    <svg viewBox="0 0 48 48" width={taille} height={taille} role="img" aria-label="Dialyse" className="shrink-0 rounded-full bg-white">
      <path d="M24 7c-6.5 8.2-11 14-11 20a11 11 0 0 0 22 0c0-6-4.5-11.8-11-20Z" fill="#03316E" />
      <path d="M11 28h8l3-6 4 11 3-5h8" fill="none" stroke="#FF7A0A" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Logo({ taille = 44, clair = false, nom = true }) {
  return (
    <span className="inline-flex items-center gap-2">
      <Embleme taille={taille} />
      {nom && <span className={`font-display text-xl font-extrabold tracking-tight ${clair ? "text-white" : "text-emeraude"}`}>Dia<span className="text-citron">lyse</span></span>}
    </span>
  );
}
