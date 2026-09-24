# ADR-019: Phase 12 foundation — ephemeral EKS, Vault KMS auto-unseal, managed vector-store hosting

Status: Accepted (Stages 12.0–12.1 implemented — Makefile/pre-commit
reconstruction, trivy-action SHA pin, two-stack Terraform for
bootstrap + cluster. Stages 12.2 onward not yet built — see
docs/PHASE_12_IMPLEMENTATION_PLAN.md for current status.)

## Context

Phase 11 (ADR-018) shipped the full test suite. `.github/workflows/deploy.yml`
already assumes AWS EKS + ECR + Helm with dev/staging/production GitHub
Environments, and `infra/k8s/network-policies/README.md` (Phase 10)
explicitly deferred standing up the actual Helm chart, ingress, and
Aiven external-endpoint egress reconciliation to Phase 12. Three things
needed deciding before any of that could be built, because each one
reshapes what the Terraform/Helm actually look like.

## Decisions

### 1. EKS runs for review windows, not continuously

**Decision:** Build real Terraform + a real Helm chart targeting AWS
EKS (matching what deploy.yml already assumes), but `terraform apply`
only when the deployment needs to be demonstrated/reviewed, and
`terraform destroy` after. Not an always-on production cluster.

**Why:** EKS control plane alone is billed continuously
(~$0.10/hour) regardless of load, before counting nodes, NAT gateway,
and load balancer cost. For a project whose own architecture already
shows a consistent preference for managed/on-demand services over
paying for idle self-hosted infrastructure (Aiven for Postgres/Kafka
per ADR-009, Hugging Face Inference Endpoints over a standing
embedding pod per ADR-012), running a Kubernetes control plane 24/7
for a system with no continuous production traffic is the same
mistake in a different layer.

**Consequence:** Terraform is split into two root modules
(`infra/terraform/bootstrap/` and `infra/terraform/cluster/`) instead
of one, so that `terraform destroy` on the ephemeral half can never
delete the S3 state bucket, ECR images, or the GitHub OIDC deploy role.
See `infra/terraform/README.md` for the full rationale. This decision
is also *why* decision 3 (below) came out the way it did — a stateful
vector database has nowhere durable to live inside a cluster that gets
torn down on a cycle.

### 2. Vault stays self-hosted (BUSL), gains AWS KMS auto-unseal

**Options considered:**
- Keep self-hosted Vault, add real init/unseal + Kubernetes auth
- Switch to OpenBao (MPL-licensed fork, drop-in compatible)
- Retire Vault entirely, move to AWS Secrets Manager + KMS directly

**Decision:** Keep self-hosted Vault, but add AWS KMS auto-unseal
(`seal "awskms"` config stanza, Stage 12.4) rather than manual
`vault operator unseal`.

**Why:** Decision 1 means Vault's own pod is destroyed and recreated
every review-window cycle. Manual unseal after every single
`terraform apply` defeats the point of an on-demand cluster — someone
has to be present with the key shares every time. KMS auto-unseal
solves exactly that operational problem and is standard production
guidance for Vault-on-Kubernetes regardless of always-on-or-not, not a
novel workaround. Retiring Vault entirely (option 3) would have meant
rewriting `api-gateway/src/vault_client.py`'s existing Transit-engine
encrypt/decrypt calls — real code churn for a problem decision 2
solves without touching application code at all. OpenBao was not
picked because there's no concrete problem it fixes here that KMS
auto-unseal doesn't already solve at lower migration risk; it remains
a documented option if the BUSL license ever becomes a real constraint.

**Consequence:** `infra/terraform/cluster/pod_identity.tf` provisions
the KMS key and an EKS Pod Identity association now (Stage 12.1); the
Vault Helm release and its `seal` config are Stage 12.4, not yet built.

### 3. Weaviate and Qdrant move to managed cloud

**Decision:** Weaviate Cloud + Qdrant Cloud for production, not
self-hosted StatefulSets in EKS. `vector-store/src/dual_write_store.py`
(ADR-013) needs no code change — it already just points at whatever
`WEAVIATE_URL`/`QDRANT_URL` are configured.

**Why:** Follows directly from decision 1. A StatefulSet's PVC is
either destroyed with the cluster every review-window cycle (data
loss every time) or has to be manually retained and re-attached
outside Terraform's own lifecycle (real operational complexity to
save infrastructure cost that managed cloud already solves via a free
tier at this project's data scale). Self-hosting either database only
made sense under an always-on-cluster assumption that decision 1
rejected.

**Consequence:** No Weaviate/Qdrant StatefulSets, PVCs, or backup
CronJobs in the Phase 12 Helm chart (Stage 12.2). DR is Weaviate Cloud
+ Qdrant Cloud's own backup guarantees plus the existing dual-write
pattern, not a self-hosted `dr_switch_to_qdrant.sh` failover between
two in-cluster databases (Stage 12.7 revisits whether that script is
still needed at all now, or just needs pointing at two cloud
endpoints instead of two in-cluster services).

## Also fixed this stage, independent of the above

`aquasecurity/trivy-action@master` in `.github/workflows/ci.yml`'s
`security-scan` job (flagged as an unfixed hygiene gap in ADR-018) is
pinned to `57a97c7e7821a5776cebc9bb87c984fa69cba8f1` (v0.35.0). This
wasn't waiting on any Phase 12 decision — trivy-action was actually
compromised via tag hijacking twice in March 2026 (CVE-2026-33634);
every tag from v0.0.1 through v0.34.2 was force-pushed with malicious
code during the attack window, and v0.35.0 is the specifically
confirmed-safe release per the GitHub Security Advisory.

## Not decided here

Ingress technology (AWS Load Balancer Controller vs. ingress-nginx +
cert-manager), a domain name for TLS, and cluster sizing based on
Stage 11.2's actual measured Locust throughput are all open — see
docs/PHASE_12_IMPLEMENTATION_PLAN.md.
