// Lecteur PDF interne : le document s'affiche dans l'application avec pour seules actions « Imprimer » et « Fermer » (jamais de téléchargement).
import { Printer } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { chargerPdf } from "../lib/api.js";
import Bouton from "./Bouton.jsx";
import Modal from "./Modal.jsx";

export default function PdfInterne({ titre, chemin, onFermer }) {
  const [url, setUrl] = useState("");
  const [erreur, setErreur] = useState("");
  const cadre = useRef(null);
  useEffect(() => {
    let adresse = "";
    chargerPdf(chemin).then((u) => { adresse = u; setUrl(u); }).catch((e) => setErreur(e.message));
    return () => { if (adresse) URL.revokeObjectURL(adresse); };       // libère la mémoire à la fermeture
  }, [chemin]);
  return (
    <Modal titre={titre} large onFermer={onFermer} pied={<>
      <Bouton icone={Printer} variante="principal" disabled={!url} onClick={() => cadre.current?.contentWindow?.print()}>Imprimer</Bouton>
      <Bouton onClick={onFermer}>Fermer</Bouton></>}>
      {erreur ? <p className="text-rose-700 text-sm">{erreur}</p> : !url ? <div className="py-10 flex justify-center"><span className="jauge" /></div>
        : <iframe ref={cadre} title={titre} src={url + "#toolbar=0&navpanes=0"} className="w-full h-[60dvh] rounded-lg ring-1 ring-encre/10" />}
    </Modal>
  );
}
