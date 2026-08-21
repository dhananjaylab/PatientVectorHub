#!/usr/bin/env bash
# Run from the dashboard/ directory. Deletes the files responsible for
# the two issues found in signoff review — see accompanying notes.
set -euo pipefail

# 1. Stale compiled .js/.jsx mirrors of every .ts/.tsx source file.
#    Root cause: tsconfig.json was missing "noEmit": true, so `tsc -b`
#    (run by both `npm run typecheck` and `npm run build`) was emitting
#    real .js output next to every source file on every single run.
#    Fixed in tsconfig.json (attached) — deleting these first is still
#    necessary, they won't regenerate once tsconfig.json is replaced,
#    but old ones already committed need removing by hand once.
find src \( -name "*.js" -o -name "*.jsx" \) -print -delete | while read -r f; do
  base="${f%.js}"; base="${base%.jsx}"
  if [ ! -f "${base}.ts" ] && [ ! -f "${base}.tsx" ]; then
    echo "WARNING: deleted $f but found no .ts/.tsx sibling — check this wasn't a real file" >&2
  fi
done

# 2. Competing vitest.config.ts — Vitest prefers this over vite.config.ts
#    when both exist, silently discarding the merged test config
#    (clearMocks: true, globals: false, setupFiles pointing at
#    src/test/setup.ts) documented in ADR-016.
rm -f vitest.config.ts

# 3. Thin pre-Phase-9 test-setup stub this competing config pointed at
#    instead of src/test/setup.ts.
rm -f src/test-setup.ts src/test-setup.js

# 4. Old playwright.config.js — replaced by the attached playwright.config.ts.
rm -f playwright.config.js

echo "Done. Now copy in the attached tsconfig.json, package.json, and playwright.config.ts."
