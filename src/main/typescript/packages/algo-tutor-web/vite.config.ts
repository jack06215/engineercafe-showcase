import { tanstackRouter } from '@tanstack/router-plugin/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// The algo_tutor API (`bazel run //packages/algo_tutor:serve`). SPEC §3.1:
// in the PoC the UI runs on Vite's port and forwards /api to it.
const API = 'http://127.0.0.1:4317';

// https://vite.dev/config/
export default defineConfig({
  base: '/',
  define: {
    APP_VERSION: JSON.stringify(process.env.npm_package_version),
  },
  resolve: {
    // The `@/*` alias from tsconfig.app.json.
    tsconfigPaths: true,
  },
  server: {
    // The API's Origin check (SPEC §15) allows exactly this port.
    port: 5173,
    strictPort: true,
    proxy: {
      // The API accepts only a Host of 127.0.0.1/localhost on its own port
      // (SPEC §15), so changeOrigin rewrites Host to the target's. It leaves
      // Origin alone: the API allows Vite's http://127.0.0.1:5173 and
      // http://localhost:5173 there.
      '/api': { target: API, changeOrigin: true },
    },
  },
  plugins: [
    // Generates src/routeTree.gen.ts from src/routes/ and splits each route's
    // component into its own chunk. Has to come before react().
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react({ jsxImportSource: '@emotion/react' }),
  ],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
  },
});
