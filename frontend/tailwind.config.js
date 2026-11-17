/**
 * Charte graphique reprise de ZandGo (17/11/2026, demande du propriétaire) : bleu nuit, bleu marine, orange, fond bleuté, Montserrat.
 *   encre    : bleu nuit (texte, barre latérale, bandeaux sombres)       citron : orange (accent, élément actif, pastilles)
 *   emeraude : bleu marine #03316E (actions, liens, barres de graphique)  brume  : fond clair bleuté des pages
 *   ardoise  : texte secondaire
 * Les anciens noms « nuit » et « turquoise » (utilisés dans les écrans) pointent vers ces mêmes couleurs.
 */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        encre: { DEFAULT: "#0A1E3D", 700: "#13294D", 600: "#20395F" },
        emeraude: { DEFAULT: "#03316E", 50: "#E8EEF7", 100: "#C9D6EA", 500: "#03316E", 600: "#022859", 700: "#021F45" },
        citron: { DEFAULT: "#FF7A0A", 300: "#FFC08A", 500: "#FF7A0A", 600: "#E0650A" },
        brume: "#F3F5F9",
        ardoise: "#56627A",
        nuit: "#0A1E3D",
        turquoise: { 50: "#E8EEF7", 100: "#C9D6EA", 500: "#03316E", 600: "#03316E", 700: "#022859" },
        sel: "#f6a35b",
      },
      fontFamily: {
        // Montserrat partout (texte, navigation) ; Playfair Display en italique pour les titres « éditoriaux » des bandeaux
        display: ["Montserrat", "system-ui", "sans-serif"],
        sans: ["Montserrat", "system-ui", "sans-serif"],
        editorial: ['"Playfair Display"', "Georgia", "serif"],
      },
      keyframes: { monte: { from: { transform: "translateY(12px)", opacity: "0" }, to: { transform: "none", opacity: "1" } } },
      animation: { monte: "monte .25s ease-out" },
    },
  },
  plugins: [],
};
