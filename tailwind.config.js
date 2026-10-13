// Builds static/css/tailwind.css (replaces the in-browser cdn.tailwindcss.com JIT).
// Rebuild after adding Tailwind classes to templates or JS:
//   npx tailwindcss@3.4.17 -c tailwind.config.js -i static/css/tailwind.src.css -o static/css/tailwind.css --minify
module.exports = {
  content: ['./templates/**/*.html', './static/js/**/*.js'],
  safelist: [],
  theme: { extend: {} },
  plugins: [],
};
