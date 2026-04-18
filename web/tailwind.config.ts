import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        shell: {
          50: "#fbfaf7",
          100: "#f4f0e8",
          200: "#e8e0d3",
          300: "#d2c5b1",
          500: "#8d6e4a",
          700: "#4a3a2c",
          900: "#221c18"
        },
        accent: {
          100: "#d7f2ee",
          500: "#0f766e",
          700: "#115e59"
        }
      },
      boxShadow: {
        shell: "0 22px 65px rgba(35, 28, 22, 0.08)"
      },
      fontFamily: {
        display: ["var(--font-manrope)", "sans-serif"],
        mono: ["var(--font-ibm-plex-mono)", "monospace"]
      }
    }
  },
  plugins: []
};

export default config;
