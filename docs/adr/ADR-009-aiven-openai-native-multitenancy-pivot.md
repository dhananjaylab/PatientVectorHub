# ADR-009: Managed-Cloud Dev Stack, OpenAI Embeddings, and Weaviate Native Multi-Tenancy

**Date:** 2026-07-18
**Status:** Accepted (retroactive — documents a pivot already reflected in the Phase 1 codebase)
**Supersedes:** Parts of ADR-001 through ADR-008 (docs 07–12), the embedding decision in
the pre-implementation brainstorm ("Decisions to Confirm"), and the per-tenant Weaviate
collection design in docs 05, 19–24, and 25–30.

---

## Context

The original architecture set (docs 01–42) specified an enterprise, fully self-hosted
stack: AWS EKS, CloudNativePG, Strimzi-managed Kafka on Kubernetes, HashiCorp Vault HA
Raft, Kong Gateway, AWS S3, and a self-hosted `clinical-bert` embedding pod — with the
explicit rationale that self-hosted embeddings keep PHI in-network and avoid per-vector
managed-service costs at 1.5B-document scale.

Phase 1 implementation (this repository) instead targets a **Windows-friendly, cloud-managed
development stack** intended to get a solo/small-team build running quickly against managed
services rather than a full EKS cluster. Three concrete deviations from the documented
decisions have shipped in Phase 1 code and need to be reconciled in the docs rather than
left as silent drift:

1. **Embedding provider defaults to OpenAI, not self-hosted clinical-bert.**
2. **Local/cloud infra targets Aiven-managed Postgres/Kafka + Cloudflare R2, not
   AWS RDS/MSK/S3.**
3. **Weaviate uses native multi-tenancy (one collection, shard-per-tenant) instead of
   one collection per tenant (`PatientDocument_{tenant_id}`).**

## Decision

### 1. Embeddings: OpenAI `text-embedding-3-large` as the default provider

`EMBEDDING_PROVIDER=openai` / `EMBEDDING_MODEL_VERSION=text-embedding-3-large` in both
`.env.example` and `.env.example.cloud`. The `ingestion/embedding-server/` FastAPI service
still exists and boots (per its Dockerfile and `main.py`), but its `/embed` endpoint
returns zero-vector stubs unless a real clinical-bert model is loaded — it is not wired
into the ingestion path yet.

**Why:** Faster path to a working RAG pipeline without standing up a GPU-capable pod during
early development; avoids the model cold-start/liveness risk called out in the brainstorm's
risk register ("clinical-bert pod slow to start — blocks ingestion workers on boot") entirely
during Phase 1–6 by deferring it.

**Trade-off — and this is the one that needs sign-off, not just documentation:** the
decisions doc's recommendation to self-host was explicitly a PHI/compliance decision
("PHI stays in-network"), not a performance one. Routing document text through OpenAI's
embeddings API sends clinical text off-infrastructure. This is acceptable for the current
synthetic-data-only Phase 1–6 development (no real PHI exists yet), but **must not carry
into any environment handling real patient data without one of:**
- a signed BAA with OpenAI covering the embeddings endpoint, or
- switching back to the self-hosted `clinical-bert` path before real PHI ingestion begins.

The self-hosted path is retained as the "future optional path" per the README and should be
the default the moment real PHI is in scope.

### 2. Infra: Aiven-managed services + Cloudflare R2, not AWS EKS/RDS/MSK/S3

`.env.example.cloud` and the README's "Cloud Initialization Order" target Aiven-managed
PostgreSQL and Kafka, Weaviate Cloud / self-hosted EC2, Qdrant Cloud / self-hosted EC2, and
Cloudflare R2 for object storage — not the AWS RDS Multi-AZ / AWS MSK / CloudNativePG-on-EKS /
Strimzi / S3 stack described in ADR-001–008 and doc 29's Terraform modules.

**Why:** Removes the EKS cluster and Terraform bring-up as a Phase 1 dependency, lets
development proceed against managed services reachable from a single developer machine
(including Windows, per the `.ps1`/`.bat` dev scripts), and avoids AWS-specific lock-in
this early. Cloudflare R2 specifically avoids S3 egress costs.

**Trade-off:** the existing Terraform modules (`infra/terraform/modules/{eks,s3,iam}`) and
Strimzi `KafkaTopic` CRDs documented in doc 11 and 38 are not exercised by anything in this
repo yet. They are not wrong, just unused for now — they remain the target for the
Phase 12 production deployment doc (42) unless a further ADR changes the production target
to a fully managed-service architecture as well. **Open question, not yet decided:** does
production stay on EKS as planned, or does the Aiven/R2 pattern extend to production too?
This ADR does not resolve that — it only documents the dev-stack pivot.

### 3. Weaviate: native multi-tenancy, not per-tenant collections

`scripts/setup_weaviate_schema.py` creates a single shared `PatientDocument` collection with
`multi_tenancy_config=Configure.multi_tenancy(enabled=True, auto_tenant_creation=True)` and
scopes every read/write via `collection.with_tenant(tenant_id)`, rather than the
`PatientDocument_{tenant_id}` per-tenant collection naming in docs 05, 19, and 25.

**Why:** Native multi-tenancy is Weaviate's current recommended pattern for exactly this
shape of problem (many tenants, shared schema) — it avoids collection-count sprawl at
11M-patient scale, and `auto_tenant_creation=True` removes the need for a tenant
pre-registration step. Cross-tenant reads are structurally impossible (shard-level
isolation enforced by Weaviate itself), which is at least as strong an isolation guarantee
as the naming-convention approach.

**Trade-off:** any RAG-engine/vector-store code written against the old
`PatientDocument_{tenant_id}` naming (as shown in docs 25–30's `weaviate_store.py` sample
and `NamespaceManager.weaviate_class()`) must be rewritten to call `.with_tenant(tenant_id)`
on the single `PatientDocument` collection instead. This has not yet happened — `vector-store/`
in Phase 1 only defines the interface (`VectorStoreInterface`), not the Weaviate
implementation, so there is no stale code to fix yet, but the docs referencing the old
naming should be treated as superseded before Phase 6 implementation begins.

## Consequences

- Docs 02 (TRD), 05 (Schema — Vector Store Schema section), 12 (ADR-003), 20, and 25–30
  should be marked superseded by this ADR for the items above, rather than left as the
  source of truth for Phase 6+ implementation.
- The brainstorm doc's Decision Card "Embedding approach for MVP" recommendation
  (self-hosted, checked) should be flagged as **reversed for Phase 1–6 dev only**, with an
  explicit re-confirmation gate before any real PHI ingestion.
- No change to RLS, audit logging, or RBAC decisions — those remain as documented and are
  independent of this pivot.
- Production target (EKS vs. managed-services-throughout) remains an open decision and
  should get its own ADR before Phase 12 planning is finalized.

## References

- `README.md` (Configuration, Cloud Initialization Order)
- `.env.example.cloud`
- `scripts/setup_weaviate_schema.py`
- `ingestion/embedding-server/main.py`
- Pre-implementation brainstorm — "Decisions to Confirm" (Embedding approach for MVP)
- Docs 07–12 — ADR-001 through ADR-008
