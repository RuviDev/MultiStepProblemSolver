/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "primary-accent": "#2c72ff",
        "secondary-accent": "#ffffff",
        "tertiary-accent": "#000000",
        "dark-base": "#3779f0",
        "light-base": "#bfd6fc",
        "light-ash": "#fcfcfc",
        "ash": "#ebebeb"
      },
    },
  },
  plugins: [],
};
