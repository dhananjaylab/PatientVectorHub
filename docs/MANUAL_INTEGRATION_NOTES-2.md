# Manual Integration Notes

Living document — items here are either resolved (kept, marked, for
history) or still open and need a human decision/action. Not a changelog
of every phase; only things that needed manual attention beyond normal
code delivery.

## Phase 4 items — RESOLVED

Verified resolved against this phase's actual repo dump (both files are
now fully readable, correct source — not just "presumed fixed"):

- **`api-gateway/src/main.py` came through as an unreadable binary
  placeholder**, and separately had a double-`yield` bug in `lifespan()`
  once merged. Both resolved — the double-yield bug's fix is documented
  in the file's own docstring (reproduced concretely via the raw ASGI
  lifespan protocol, not just inspected). Confirmed still fixed as of
  Phase 7 (this file was edited again this phase, to mount the query
  router — see `docs/adr/ADR-014-rag-query-engine.md`).
- **`api-gateway/src/config.py` came through as an unreadable binary
  placeholder**, needing Kafka SASL/SSL fields merged in. Resolved —
  fully readable, correct source as of this dump.
- **boto3 / R2 credentials in CI** — resolved via the standing decision
  to mock `boto3` entirely in CI rather than provision live R2
  credentials; unchanged since Phase 4, still the policy as of Phase 7.

## Phase 4 item — STILL OPEN

- **`ingestion` → `vector_store` cross-package import has no packaging
  solution for local (non-Docker) dev.** Docker builds work today
  (`ingestion/Dockerfile` copies `vector-store/src/` to `./vector_store/`
  at build time). Running `ingestion` locally via `venv-ingestion`
  outside Docker does not have `vector-store/src` on its path by
  default. Two options, neither implemented:
  - **Option A:** add a minimal `setup.py`/`pyproject.toml` to
    `vector-store/`, `pip install -e vector-store/` into each venv that
    needs it (`venv-ingestion`, and as of Phase 7, `venv-rag-engine` and
    `venv-api-gateway` too — see below).
  - **Option B:** document a `PYTHONPATH` addition in each service's
    local dev instructions.
  Still a small, separate packaging decision — you may already have a
  preferred approach. Phase 7 widens the set of services this affects
  (see next section) but doesn't resolve it; `tests/conftest.py`'s new
  `_ensure_cross_package_alias()` (below) is a **test-time-only**
  workaround, not a substitute for either option above for actually
  running the services locally.

## Phase 7 items

### `rag_engine` and `vector_store` cross-package imports now reach `api-gateway` too

Same shape as the still-open `ingestion` → `vector_store` item above,
now also affecting `api-gateway`: `routers/query.py` imports
`rag_engine.retriever` and `rag_engine.synthesizer`, which themselves
import `vector_store.interface`.

- **Docker:** resolved. `api-gateway/Dockerfile` now builds from the
  repo root (was `api-gateway/` alone) and copies `rag-engine/src/` →
  `./rag_engine/` and `vector-store/src/` → `./vector_store/`, same
  pattern `ingestion/Dockerfile` already used. CI's `security-scan` job
  and `deploy.yml` both updated to build with `-f api-gateway/Dockerfile
  ... .` (repo-root context) accordingly.
- **Local (non-Docker) dev:** open, same as the Phase 4 item above —
  apply whichever of Option A / Option B you choose there to
  `venv-api-gateway` and `venv-rag-engine` as well once decided.
- **Tests:** resolved, but only for pytest specifically.
  `tests/conftest.py`'s new `_ensure_cross_package_alias()` makes
  `vector-store/src` and `rag-engine/src` importable as the top-level
  `vector_store` / `rag_engine` names during test runs, via
  `importlib.util.spec_from_file_location()` — no symlink, copy step, or
  `pip install -e` needed *for tests*. This does not help
  `uvicorn src.main:app` run locally outside pytest or Docker; that
  still needs Option A or B above.

### `api-gateway/src/errors.py` — still unreadable, but usable

Same "`[Binary file]`" issue as `main.py`/`config.py` originally hit in
Phase 4. Not resolved the same way (recreating from scratch, the way
`rag-engine/requirements.txt` was this phase) because `main.py` already
imports and uses `PVHError`/`pvh_exception_handler` from it, and getting
a recreation subtly wrong would be worse than leaving it alone.

Its contract was instead recovered from `tests/unit/test_errors.py`,
which already exercises a full exception hierarchy — including
`QueryError` and `LLMError`, both apparently added in anticipation of
this phase, since nothing before Phase 7 used either. That was enough to
use both correctly in `routers/query.py` without needing the actual
source. If you have the real file already, no action needed; nothing
delivered this phase assumes anything about it beyond what
`test_errors.py` already proves.

### `rag-engine/requirements.txt` — recreated

Also came through unreadable. Unlike `errors.py`, this was safe to
recreate fully from scratch — it's a new file for this phase, so there
was no existing content to reconcile against or risk silently
overwriting. See the file itself for pin rationale (matched to
`ingestion/requirements.txt`'s existing, already-tested pins for the
packages both share — `openai`, `huggingface_hub`, `tenacity` — plus new
pins for `anthropic` and `google-genai`, verified against the actually-
installed versions).

### `Makefile` — still unreadable, not touched

Same issue, but nothing in Phase 7 needs a `Makefile` change, so it was
left exactly as-is rather than guessed at. If you want a
`make test-query`-style convenience target, that's a manual addition,
not something this phase's delivery depends on.

### Dependency version drift noticed, not acted on

Two packages have released past this project's existing pins since they
were originally set (Phase 4/5), noticed while verifying Phase 7's own
new pins against currently-installed versions:

- `huggingface_hub` — `ingestion/requirements.txt` pins
  `<1.25.0`; currently-released is `1.25.1`.
- `openai` — `ingestion/requirements.txt` pins `<2.0.0`; currently-
  released is `2.50.0` (a new major version).

Neither was bumped. `rag-engine/requirements.txt`'s new pins for both
packages were deliberately kept at `ingestion`'s existing ceilings for
consistency, not because a bump would necessarily break anything —
simply because verifying a major-version jump (`openai` 1.x → 2.x
especially) wasn't in scope for this phase, and bumping one service's
pin without the other would leave two different versions of the same
client library in use for the same kind of call across services. Bump
both together, deliberately, if this is revisited.
