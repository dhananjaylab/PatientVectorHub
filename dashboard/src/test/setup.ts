/**
 * dashboard/src/test/setup.ts
 *
 * Loaded via vite.config.ts's `test.setupFiles`. Two things registered
 * here, both because this config deliberately runs with `globals: false`
 * (see vite.config.ts's comment) rather than the more common
 * `globals: true` Vitest setup:
 *
 *  1. jest-dom matchers (toBeInTheDocument, etc.) — imported for side
 *     effects, extends Vitest's `expect`.
 *  2. @testing-library/react's automatic post-test unmount/cleanup only
 *     self-registers when it detects a global `afterEach` — which does
 *     NOT exist with globals:false. Without the explicit
 *     `afterEach(cleanup)` below, every test file would leak mounted
 *     components into the next test, causing exactly the kind of
 *     cross-test state bleed and duplicate-element query failures the
 *     testing-library ecosystem's own docs warn about.
 */
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

afterEach(() => {
  cleanup()
})
