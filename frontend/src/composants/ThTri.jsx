// En-tête de colonne triable (règle 19) : ⇅ discret, ▲ / ▼ sur la colonne triée (en-tête orange).
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

export default function ThTri({ cle, tri, children, numerique = false }) {
  const actif = tri.cle === cle && tri.sens !== 0;
  return (
    <th className={`${numerique ? "num" : ""} ${actif ? "trie" : ""}`} aria-sort={actif ? (tri.sens === 1 ? "ascending" : "descending") : "none"}>
      <button onClick={() => tri.basculer(cle)} className={`inline-flex items-center gap-1 font-semibold ${numerique ? "flex-row-reverse" : ""}`} title="Trier cette colonne">
        {children}
        {actif ? (tri.sens === 1 ? <ArrowUp size={14} /> : <ArrowDown size={14} />) : <ArrowUpDown size={13} className="opacity-40" />}
      </button>
    </th>
  );
}
