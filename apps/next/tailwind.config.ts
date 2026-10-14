import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  // DSFR fournit son propre reset — on désactive le preflight Tailwind
  // pour éviter les conflits de styles globaux.
  corePlugins: {
    preflight: false,
  },
  plugins: [],
};

export default config;
