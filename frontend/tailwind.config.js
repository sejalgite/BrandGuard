/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f7ff",
          100: "#e0effe",
          200: "#b9ddfe",
          300: "#7cc2fd",
          400: "#36a3fa",
          500: "#0c87eb",
          600: "#0069c7",
          700: "#0154a1",
          800: "#054785",
          900: "#0a3c6e",
          950: "#07264a",
        },
      },
    },
  },
  plugins: [],
};

