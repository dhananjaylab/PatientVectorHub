#!/usr/bin/env python3
"""
Phase 4 done-criteria smoke test: prove the pipeline doesn't fall over at
~10,000 documents. This is NOT the full Locust harness with SLA gates —
that's Phase 11. This talks directly to the DB + Celery layer (bypassing
the inline-JSON-body HTTP API, which isn't meant for 10k-document
payloads — see api-gateway/src/schemas/ingest.py's docstring) to dispatch
a large batch and report dispatch time.

Prerequisite: upload ONE small real text file to R2 first (all 10k
documents reuse it, since this is a throughput smoke test, not a content
test):
  r2://<R2_DOCUMENT_BUCKET>/seed/load-test/synthetic.txt

Usage:
  python scripts/load_test_ingestion.py --count 10000 \
      --tenant 00000000-0000-0000-0000-000000000001

Then poll completion with:
  SELECT status, doc_count_processed, doc_count_failed, doc_count_total
  FROM ingestion_jobs WHERE id = '<job_id printed below>';
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vector-store"))

from sqlalchemy import text  # noqa: E402

from src.db.session import get_tenant_sync_session  # noqa: E402
from src.workers.batch_worker import process_document  # noqa: E402


def main(tenant_id: str, count: int, r2_uri: str) -> None:
    job_id = str(uuid.uuid4())
    with get_tenant_sync_session(tenant_id) as db:
        db.execute(text(
            "INSERT INTO ingestion_jobs (id, name, status, source_type, doc_count_total, tenant_id)"
            " VALUES (:id, 'load-test', 'queued', 's3_batch', :n, :tid)"
        ), {"id": job_id, "n": count, "tid": tenant_id})

        patient_ids = [
            r[0] for r in db.execute(
                text("SELECT id FROM patients WHERE tenant_id = :tid LIMIT 1000"),
                {"tid": tenant_id},
            )
        ]
    if not patient_ids:
        print("No patients found for this tenant — run scripts/seed_data.py first.")
        sys.exit(1)

    print(f"Job {job_id}: dispatching {count} documents (tenant {tenant_id})...")
    start = time.time()
    for i in range(count):
        doc_id = str(uuid.uuid4())
        patient_id = str(patient_ids[i % len(patient_ids)])
        with get_tenant_sync_session(tenant_id) as db:
            db.execute(text(
                "INSERT INTO documents (id, patient_id, document_type, source_path,"
                " ingestion_job_id, embedding_status, tenant_id)"
                " VALUES (:id, :pid, 'clinical_note', :src, :jid, 'pending', :tid)"
            ), {"id": doc_id, "pid": patient_id, "src": r2_uri, "jid": job_id, "tid": tenant_id})
        process_document.delay(
            doc_id=doc_id, tenant_id=tenant_id, job_id=job_id,
            r2_uri=r2_uri, document_type="clinical_note",
        )
        if (i + 1) % 500 == 0:
            elapsed = time.time() - start
            print(f"  dispatched {i + 1}/{count}  ({(i + 1) / elapsed:.1f} docs/sec so far)")

    total_elapsed = time.time() - start
    print(f"\nDispatch complete: {count} documents in {total_elapsed:.1f}s "
          f"({count / total_elapsed:.1f} docs/sec dispatch rate).")
    print(f"Job ID: {job_id}")
    print(
        "Poll processing completion with:\n"
        f"  SELECT status, doc_count_processed, doc_count_failed, doc_count_total\n"
        f"  FROM ingestion_jobs WHERE id = '{job_id}';"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--tenant", default="00000000-0000-0000-0000-000000000001")
    parser.add_argument(
        "--r2-uri", default="r2://pvh-documents-dev/seed/load-test/synthetic.txt",
        help="A single small text file already uploaded to R2; reused for every document.",
    )
    args = parser.parse_args()
    main(args.tenant, args.count, args.r2_uri)
