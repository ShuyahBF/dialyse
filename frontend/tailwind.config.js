/** Palette sobre de la clinique : bleu nuit (texte), turquoise (action), orange (sélection), vert / rouge (états). */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: { nuit: "#0A1E3D", turquoise: { 50: "#ecfeff", 100: "#cffafe", 500: "#0891b2", 600: "#0e7490", 700: "#155e75" }, sel: "#f6a35b" },
      fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "Roboto", "sans-serif"] },
    },
  },
  plugins: [],
};
