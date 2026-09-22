"""
tests/load/check_dispatch_rate.py — Phase 11 / ADR-018 Stage 11.2.

Parses Locust's --csv output and enforces the CI dispatch-rate gate.

Deliberately does NOT trust the stats CSV's own "Requests/s" column for
this: verified directly (running Locust against a local stub server)
that column reflects an instantaneous rate sampled at the moment the
CSV is written, which decays toward 0 right as the run stops -- not a
run-average. Computing `request_count / run_time_seconds` from the
known --run-time value is the correct, verified way to get the actual
sustained rate.

Usage (matches the CI step this runs from):
    locust -f tests/load/locustfile.py --headless \
        --host http://localhost:8000 \
        --users 50 --spawn-rate 10 --run-time 60s \
        --csv tests/load/results/dispatch_rate
    python tests/load/check_dispatch_rate.py \
        tests/load/results/dispatch_rate_stats.csv \
        --run-time-seconds 60 \
        --min-dispatch-rate 20 \
        --max-failure-pct 5.0
"""

from __future__ import annotations

import argparse
import csv
import sys

# Matches the route this gate cares about -- ingest.py's create_job,
# not the query route (QueryUser exists to exercise retrieval latency
# under concurrent load, not to gate a throughput number).
_TARGET_ROUTE_NAME = "/v1/ingest/jobs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stats_csv", help="Locust's *_stats.csv output path")
    parser.add_argument("--run-time-seconds", type=float, required=True)
    parser.add_argument("--min-dispatch-rate", type=float, required=True,
                         help="Minimum required requests/sec for " + _TARGET_ROUTE_NAME)
    parser.add_argument("--max-failure-pct", type=float, default=5.0,
                         help="Ties to infra/prometheus/alert_rules.yml's "
                              "5xx-rate-critical threshold (ADR-018) rather "
                              "than an independently invented number")
    args = parser.parse_args()

    with open(args.stats_csv, newline="") as f:
        rows = {row["Name"]: row for row in csv.DictReader(f)}

    if _TARGET_ROUTE_NAME not in rows:
        print(f"FAIL: no stats row found for {_TARGET_ROUTE_NAME!r} -- "
              "did the target route change, or did the run fail before "
              "any requests completed?", file=sys.stderr)
        return 1

    row = rows[_TARGET_ROUTE_NAME]
    request_count = int(row["Request Count"])
    failure_count = int(row["Failure Count"])
    dispatch_rate = request_count / args.run_time_seconds
    failure_pct = (failure_count / request_count * 100) if request_count else 100.0

    print(f"{_TARGET_ROUTE_NAME}: {request_count} requests over "
          f"{args.run_time_seconds:.0f}s = {dispatch_rate:.2f} req/s "
          f"({failure_count} failures, {failure_pct:.2f}%)")

    ok = True
    if dispatch_rate < args.min_dispatch_rate:
        print(f"FAIL: dispatch rate {dispatch_rate:.2f} req/s < required "
              f"{args.min_dispatch_rate:.2f} req/s", file=sys.stderr)
        ok = False
    if failure_pct > args.max_failure_pct:
        print(f"FAIL: failure rate {failure_pct:.2f}% > allowed "
              f"{args.max_failure_pct:.2f}%", file=sys.stderr)
        ok = False

    if ok:
        print("PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
