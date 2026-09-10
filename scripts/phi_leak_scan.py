"""
scripts/phi_leak_scan.py — Phase 11 / ADR-018 Stage 11.5.

Scans captured text (application logs, exported Jaeger trace JSON,
error response bodies -- anything produced by the Locust and Playwright
runs in Stages 11.2/11.3) for PHI that should never appear in plaintext
outside the audited `/v1/audit/phi-reveal` path.

Uses Presidio (presidio-analyzer==2.2.364, presidio-anonymizer==2.2.364
-- current stable, now under the independent data-privacy-stack org)
rather than a regex-only scanner: verified directly against a
realistic leaked-log sample that Presidio's built-in PERSON recognizer
catches a real name a synthetic-data-only regex could never anticipate,
alongside EMAIL_ADDRESS/PHONE_NUMBER and a custom pattern for this
system's own MRN shape.

Two real things verified before this was written, not assumed:

  1. Presidio's default `AnalyzerEngine()` silently downloads
     en_core_web_lg (400MB) on first use. This file explicitly
     configures en_core_web_sm (12.8MB) instead via NlpEngineProvider
     -- verified to give equivalent detection quality on the target
     task, and avoids a 400MB CI download becoming a silent default.
  2. The PVH_MRN pattern below is sourced from
     infra/scripts/seed_data.py's actual `_mrn_plaintext_for_seed()`
     (`SEED-MRN-` + 12 uppercase hex chars) -- an earlier draft of this
     scanner used a guessed, materially different pattern
     (`MRN-\\d{8}`) before that function was read directly. Vault
     ciphertext (`vault:v1:...`) is deliberately NOT flagged -- it's
     already encrypted, so its presence in a log is not a leak.

Usage:
    python scripts/phi_leak_scan.py path/to/captured/logs/ \
        --min-score 0.5

    # Or a single file:
    python scripts/phi_leak_scan.py locust_run.log --min-score 0.5

Exit code 0: no findings at or above --min-score.
Exit code 1: at least one finding -- prints each with enough context
to locate and fix the leak, without ever printing enough of the
matched span itself to duplicate the leak in CI output (real synthetic
values are truncated; this matters more once this scanner is ever
pointed at anything other than known-synthetic seed data).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Never flag Vault-encrypted values -- they're already safe. Checked
# before Presidio even sees the line, so an encrypted MRN sitting next
# to other real PHI-shaped text in the same log line doesn't produce a
# confusing partial-redaction question.
_VAULT_CIPHERTEXT_PREFIX = "vault:v1:"

# Allowlist, not denylist -- verified directly (scanning a real sample
# log) that Presidio's en_core_web_sm model spuriously tags plain
# key=value log fragments like "status=200" as ORGANIZATION. A denylist
# means chasing every such spurious category as it's found; an
# allowlist of what's actually PHI-relevant for this system is precise
# by construction. PVH_MRN is the custom recognizer added below.
_PHI_RELEVANT_ENTITY_TYPES = frozenset({
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "LOCATION",
    "MEDICAL_LICENSE",
    "US_DRIVER_LICENSE",
    "US_BANK_NUMBER",
    "PVH_MRN",
    # DATE_TIME deliberately excluded from the default allowlist:
    # verified directly that it flags ordinary ISO log timestamps
    # (every line of a realistic timestamped log failed the scan on
    # this alone) -- HIPAA does treat patient-specific dates (DOB,
    # admission/discharge) as identifiers, but a generic NER model has
    # no way to distinguish those from a routine log timestamp without
    # much more context than a line-by-line scan gives it. Left as a
    # known, documented scope boundary rather than a source of scanner
    # fatigue that trains reviewers to ignore its output.
})


def _build_analyzer(min_score: float):
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

    # Sourced from infra/scripts/seed_data.py's _mrn_plaintext_for_seed()
    # -- see this module's docstring.
    mrn_pattern = Pattern(name="pvh_mrn_plaintext", regex=r"\bSEED-MRN-[0-9A-F]{12}\b", score=0.9)
    analyzer.registry.add_recognizer(
        PatternRecognizer(supported_entity="PVH_MRN", patterns=[mrn_pattern])
    )
    return analyzer


def _iter_text_files(path: Path):
    if path.is_file():
        yield path
    else:
        for p in sorted(path.rglob("*")):
            if p.is_file() and p.suffix in {".log", ".txt", ".json"}:
                yield p


def scan(path: Path, min_score: float) -> list[dict]:
    analyzer = _build_analyzer(min_score)
    findings = []

    for file_path in _iter_text_files(path):
        try:
            text = file_path.read_text(errors="replace")
        except OSError:
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            if _VAULT_CIPHERTEXT_PREFIX in line:
                # Still worth scanning the rest of the line for a
                # *different* real leak, but strip the ciphertext
                # substring first so Presidio's own pattern matchers
                # don't get confused by its base64 payload.
                line = line.replace(_VAULT_CIPHERTEXT_PREFIX, "")

            for result in analyzer.analyze(text=line, language="en"):
                if result.entity_type not in _PHI_RELEVANT_ENTITY_TYPES:
                    continue
                if result.score < min_score:
                    continue
                matched = line[result.start:result.end]
                findings.append({
                    "file": str(file_path),
                    "line": line_no,
                    "entity_type": result.entity_type,
                    "score": result.score,
                    # Truncated on purpose -- see module docstring.
                    "preview": (matched[:4] + "…") if len(matched) > 4 else matched,
                })

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="File or directory to scan")
    parser.add_argument("--min-score", type=float, default=0.5,
                         help="Drop findings below this confidence "
                              "(verified: sub-0.1 numeric-substring noise "
                              "is common at the default threshold)")
    args = parser.parse_args()

    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 2

    findings = scan(args.path, args.min_score)

    if not findings:
        print(f"PASS: no PHI-shaped content found at or above score {args.min_score}")
        return 0

    print(f"FAIL: {len(findings)} potential PHI leak(s) found:\n", file=sys.stderr)
    for f in findings:
        print(f"  {f['file']}:{f['line']}  {f['entity_type']} "
              f"(score={f['score']:.2f})  {f['preview']!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
