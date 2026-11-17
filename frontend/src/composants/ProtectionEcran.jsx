// Protection de l'écran (données de santé) : touche Impr. écran neutralisée, contenu flouté quand la page perd le focus, clic droit interdit.
// Limite à rappeler : un site web ne peut pas bloquer une capture faite par le système ou le téléphone.
import { useEffect, useState } from "react";

export default function ProtectionEcran({ children }) {
  const [flou, setFlou] = useState(false);
  useEffect(() => {
    const perd = () => setFlou(true), gagne = () => setFlou(false);
    const touche = (e) => {
      if (e.key === "PrintScreen") {
        setFlou(true);
        try { navigator.clipboard.writeText(""); } catch { /* presse-papiers refusé */ }
        setTimeout(() => setFlou(false), 2500);
      }
    };
    const visibilite = () => setFlou(document.hidden);
    const menu = (e) => e.preventDefault();
    window.addEventListener("blur", perd); window.addEventListener("focus", gagne);
    window.addEventListener("keyup", touche); document.addEventListener("visibilitychange", visibilite);
    document.addEventListener("contextmenu", menu);
    return () => {
      window.removeEventListener("blur", perd); window.removeEventListener("focus", gagne);
      window.removeEventListener("keyup", touche); document.removeEventListener("visibilitychange", visibilite);
      document.removeEventListener("contextmenu", menu);
    };
  }, []);
  return (
    <>
      <div className={flou ? "ecran-flou" : ""}>{children}</div>
      {flou && <div className="fixed inset-0 z-50 flex items-center justify-center text-nuit font-semibold pointer-events-none">Contenu protégé — revenez sur la fenêtre</div>}
    </>
  );
}
