// dashboard/eslint.config.js
//
// Phase 9 addition. There was no .eslintrc.* in this repo before this
// phase — package.json's old `lint` script (`eslint src/ --ext .ts,.tsx`)
// referenced flags/config-resolution behavior from ESLint's legacy
// (pre-v9) config system, but no legacy config file ever existed to back
// it up. Written directly as flat config rather than "migrated" from
// something, because there was nothing to migrate: ESLint 8 has been EOL
// for a long time, and as of 2026-08-06 ESLint 9 is EOL too — v10 only
// supports flat config, so this is the only form that works with the
// version pinned in package.json.
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'coverage', 'playwright-report', 'test-results'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Vite's fast-refresh boundary check — allow constant exports
      // (e.g. a component file that also exports a small config object)
      // rather than forcing every file to export exactly one component.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      // Route-guard / RBAC helpers intentionally return `unknown`-shaped
      // JWT claim data in a couple of places (see lib/keycloak.ts) —
      // blanket-banning `any` there would just push the same escape
      // hatch into `as unknown as X` casts, which are harder to grep for.
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
  {
    // Playwright specs run under Node/Playwright's own test runner, not
    // the browser — separate globals, and they legitimately use
    // test-fixture patterns ESLint's browser ruleset doesn't need to see.
    files: ['e2e/**/*.ts'],
    languageOptions: {
      globals: globals.node,
    },
  },
)
