// Tests des fonctions pures : tri (règle 19), libellés de menu (règle 18), dates et version (règle 2).
import assert from "node:assert/strict";
import { trierLignes } from "../src/lib/tri.js";
import { criteresMotDePasse, motDePasseAssezFort } from "../src/lib/motdepasse.js";
import { ajouterJours, dateFr, libelleVersion, nb, titreMenu } from "../src/lib/format.js";

let n = 0;
const ok = (nom, f) => { f(); n++; console.log("OK  ", nom); };

ok("tri croissant / décroissant, accents ignorés", () => {
  const l = [{ nom: "Élodie" }, { nom: "Zoé" }, { nom: "Edgar" }];
  assert.deepEqual(trierLignes(l, "nom", 1).map((x) => x.nom), ["Edgar", "Élodie", "Zoé"]);
  assert.deepEqual(trierLignes(l, "nom", -1).map((x) => x.nom), ["Zoé", "Élodie", "Edgar"]);
});
ok("tri : sens 0 = ordre d'origine", () => {
  const l = [{ a: 3 }, { a: 1 }];
  assert.deepEqual(trierLignes(l, "a", 0), l);
});
ok("tri : les valeurs vides restent en dernier dans les DEUX sens", () => {
  const l = [{ a: "" }, { a: 2 }, { a: null }, { a: 10 }];
  assert.deepEqual(trierLignes(l, "a", 1).map((x) => x.a), [2, 10, "", null]);
  assert.deepEqual(trierLignes(l, "a", -1).map((x) => x.a), [10, 2, "", null]);
});
ok("tri : les nombres se comparent numériquement (10 > 9)", () => {
  assert.deepEqual(trierLignes([{ a: 10 }, { a: 9 }], "a", 1).map((x) => x.a), [9, 10]);
});
ok("tri : lecteur personnalisé", () => {
  assert.deepEqual(trierLignes([{ p: { n: "b" } }, { p: { n: "a" } }], "n", 1, { n: (x) => x.p.n }).map((x) => x.p.n), ["a", "b"]);
});
ok("menu : majuscule à chaque mot, sigles conservés", () => {
  assert.equal(titreMenu("tableau de bord"), "Tableau De Bord");
  assert.equal(titreMenu("postes de dialyse SAWALI"), "Postes De Dialyse SAWALI");
});
ok("dates françaises", () => {
  assert.equal(dateFr("2026-11-17"), "17/11/2026");
  assert.equal(ajouterJours("2026-12-31", 1), "2027-01-01");
  assert.equal(ajouterJours("2026-03-01", -1), "2026-02-28");
});
ok("nombres à virgule française", () => {
  assert.equal(nb(60.5), "60,5");
  assert.equal(nb(null), "");
});
ok("version : libellé court sans lot ; complet avec lot", () => {
  const v = { version: "1.1", lot: "1", deploye_le: "17/11/2026 03:00" };
  assert.equal(libelleVersion(v), "Version 1.1 · déployée le 17/11/2026 03:00");
  assert.match(libelleVersion(v, true), /^Version 1\.1 · Lot 1/);
});
ok("mot de passe : mêmes règles que le serveur (8 caractères, une lettre, un chiffre)", () => {
  assert.equal(motDePasseAssezFort("abc12345"), true);
  assert.equal(motDePasseAssezFort("abcdefgh"), false);       // pas de chiffre
  assert.equal(motDePasseAssezFort("12345678"), false);       // pas de lettre
  assert.equal(motDePasseAssezFort("abc123"), false);         // trop court
  assert.equal(motDePasseAssezFort(""), false);
  assert.deepEqual(criteresMotDePasse("abc").map((c) => c.ok), [false, true, false]);
  assert.deepEqual(criteresMotDePasse("Éa1xxxxx").map((c) => c.ok), [true, true, true]);
});
console.log(`\n${n} tests réussis`);
