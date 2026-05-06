module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"],
  safelist: [
    "bg-blue-50",
    "text-blue-700",
    "bg-amber-50",
    "text-amber-700",
    "bg-orange-50",
    "text-orange-700",
    "bg-yellow-100",
    "bg-emerald-50",
    "text-emerald-700",
    "bg-red-50",
    "text-red-700",
    "bg-slate-100",
    "text-slate-700",
  ],
  theme: {
    extend: {
      colors: {
        monster: {
          jaune: "#FFD700",
          noir: "#000000",
          gris: "#2C3E50",
        },
      },
    },
  },
  plugins: [],
};
