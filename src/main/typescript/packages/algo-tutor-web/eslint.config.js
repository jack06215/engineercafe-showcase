import eslintReact from '@eslint-react/eslint-plugin';
import js from '@eslint/js';
import prettier from 'eslint-config-prettier/flat';
import { importX } from 'eslint-plugin-import-x';
import reactHooks from 'eslint-plugin-react-hooks';
import storybook from 'eslint-plugin-storybook';
import unusedImports from 'eslint-plugin-unused-imports';
import { defineConfig, globalIgnores } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig(
  globalIgnores([
    'dist',
    'storybook-static',
    'coverage',
    'src/routeTree.gen.ts',
  ]),
  {
    files: ['**/*.{js,ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      eslintReact.configs['recommended-typescript'],
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        // Otherwise typescript-eslint guesses it from where its configs were
        // imported, and an editor's long-lived ESLint (eslint_d) that has
        // loaded several packages' configs can't tell which one applies.
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // @eslint-react re-implements these three; React's own plugin above
      // already reports them, and its disable comments are the ones used.
      '@eslint-react/exhaustive-deps': 'off',
      '@eslint-react/rules-of-hooks': 'off',
      '@eslint-react/set-state-in-effect': 'off',
      // Only says React Compiler would skip a component that calls
      // TanStack Table/Virtual. The compiler isn't enabled here; turn this
      // back on with it.
      'react-hooks/incompatible-library': 'off',
    },
  },
  storybook.configs['flat/recommended'],
  {
    files: ['src/**/*.{js,ts,tsx}'],
    plugins: { 'import-x': importX, 'unused-imports': unusedImports },
    rules: {
      'import-x/order': [
        'error',
        {
          groups: [
            'builtin',
            'external',
            'parent',
            'sibling',
            'index',
            'object',
            'type',
          ],
          pathGroups: [
            {
              pattern: '@/**',
              group: 'parent',
              position: 'before',
            },
          ],
          // Without a resolver `@/…` may be classed as an external scoped
          // package, and pathGroups never apply to excluded types.
          pathGroupsExcludedImportTypes: ['builtin'],
          alphabetize: {
            order: 'asc',
          },
          'newlines-between': 'always',
        },
      ],
      '@typescript-eslint/no-unused-vars': 'off',
      'unused-imports/no-unused-imports': 'warn',
      'unused-imports/no-unused-vars': [
        'warn',
        {
          vars: 'all',
          varsIgnorePattern: '^_',
          args: 'after-used',
          argsIgnorePattern: '^_',
        },
      ],
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
      // Emotion's css prop.
      '@eslint-react/dom-no-unknown-property': ['error', { ignore: ['css'] }],
    },
  },
  prettier,
);
