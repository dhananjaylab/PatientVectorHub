# Phase 12 Implementation Plan — Production Deployment (living status tracker)

Same pattern as `docs/PHASE_11_IMPLEMENTATION_PLAN.md`: this table is
kept current as stages land, not written once at the end. See
`docs/adr/ADR-019-...md` for why each foundational decision came out
the way it did.

## Confirmed decisions (this session)

1. EKS applies for review windows, `terraform destroy` after — not an
   always-on cluster.
2. Vault stays self-hosted (BUSL), gains AWS KMS auto-unseal — zero
   changes to existing `vault_client.py` code.
3. Weaviate + Qdrant move to Weaviate Cloud + Qdrant Cloud — no
   self-hosted StatefulSets, `dual_write_store.py` unchanged.

## Stage status

| Stage | Scope | Status |
|---|---|---|
| 12.0 | Prep: reconstruct `Makefile` + `.pre-commit-config.yaml`, pin `trivy-action` by SHA | ✅ Implemented this session |
| 12.1 | Terraform: bootstrap (state bucket, ECR, GitHub OIDC deploy role) + cluster (VPC, EKS Auto Mode, Pod Identity plumbing) | ✅ Implemented this session |
| 12.2 | Helm chart (`Chart.yaml` + `templates/`) for api-gateway, celery-worker, celery-beat, kafka-consumer; templated NetworkPolicies | 🔜 Not started |
| 12.3 | Ingress + TLS | 🔜 Not started — needs a decision: AWS Load Balancer Controller + ACM vs. ingress-nginx + cert-manager, and whether a real domain exists |
| 12.4 | Vault Helm release with `seal "awskms"`, Kubernetes auth method, policies | 🔜 Not started (KMS key + Pod Identity association already provisioned in 12.1) |
| 12.5 | Weaviate Cloud / Qdrant Cloud connection secrets, Keycloak persistence (point KC_DB at Aiven Postgres so realm/user data survives cluster teardown) | 🔜 Not started |
| 12.6 | KEDA install + `ScaledObject` for celery-worker on `pvh_kafka_consumer_lag` | 🔜 Not started — needs Stage 11.2's real measured per-worker throughput, not the roadmap's 5,000 docs/sec figure |
| 12.7 | Aiven production connectivity + NetworkPolicy egress reconciliation; revisit whether `dr_switch_to_qdrant.sh` is still needed given decision 3 | 🔜 Not started |
| 12.8 | CI/CD: Terraform plan/apply gates in GitHub Actions, image promotion flow, GitHub Environment protection rules | 🔜 Not started |
| 12.9 | Go-live checklist + runbooks | 🔜 Not started |

## What's verified vs. not, for Stages 12.0–12.1

Verified by actually running things this session:
- Every new `.tf` file parses as valid HCL (`infra/terraform/tests/test_terraform_structure.py`, 36 tests, all passing)
- The specific security/cost properties the design depends on are
  present in the actual files (state bucket hardening, ECR scan-on-push,
  OIDC trust-policy scoping, no wildcard IAM actions, S3 native locking
  not DynamoDB, Pod Identity namespace matching the real NetworkPolicies,
  EKS Auto Mode enabled, no always-on defaults) — same test file
- Every `Makefile` target dry-runs cleanly (`make -n <target>`, all 29 targets)
- `.pre-commit-config.yaml` YAML parses; every hook `rev:` is a commit
  SHA verified via `git ls-remote --tags` against the real hook repo,
  not copied from an example (one guessed SHA was caught and corrected
  during this same review — shellcheck-py's actual latest tag is
  v0.9.0.6, not the v0.10.0.1 first written)
- The `trivy-action` pin SHA (`57a97c7e...`) matches the specific
  release named as safe across multiple independent advisories for
  CVE-2026-33634

Not verified, and can't be from this sandbox (no network path to
`registry.terraform.io` or AWS):
- `terraform init` / `validate` / `plan` against the real providers
- `helm lint` (chart doesn't exist yet — Stage 12.2)
- Whether the `terraform-aws-modules/eks` v21 `access_entries` map
  shape in `eks.tf` is byte-for-byte correct — checked against the
  module's documented schema, not against the module itself

Run `terraform init && terraform validate` in both `bootstrap/` and
`cluster/` before the first real `apply` — that's the verification
step this session genuinely could not do.
