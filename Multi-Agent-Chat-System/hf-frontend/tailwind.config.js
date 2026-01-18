// tailwind.config.js

/** @type {import('tailwindcss').Config} */
export default {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}", // <-- Must include this glob pattern
    ],
    theme: {
      extend: {},
    },
    plugins: [],
  }