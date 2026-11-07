/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0f1d2e',
        navy: { 50: '#eef4fa', 100: '#d6e6f3', 600: '#1d4e89', 700: '#13315c', 800: '#0b2545', 900: '#0f1d2e' },
        sky: { 100: '#e3f2fb', 300: '#a9d6f0', 400: '#7ec3ea', 500: '#5fa8d3', 600: '#3d8cc0' },
        mist: { 50: '#f4f7fb', 100: '#eaf0f6', 200: '#d9e3ed' },
        ochre: { 500: '#c4841d', 600: '#9a6512' },
        alert: { 500: '#b42318', 600: '#912018' },
      },
      fontFamily: { sans: ['"Source Sans 3"', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'] },
    },
  },
  plugins: [],
}
