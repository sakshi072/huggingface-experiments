module.exports = {
  plugins: {
    // CRITICAL: This line tells PostCSS to run the Tailwind processor
    '@tailwindcss/postcss': {}, 
    autoprefixer: {},
  },
}