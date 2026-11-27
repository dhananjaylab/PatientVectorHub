# infra/terraform/cluster/

The ephemeral half. Apply for a review window, destroy after. Requires
`bootstrap/` to have been applied once first (see `../bootstrap/README.md`).

## Spin up for a review window

```bash
# one-time per machine, or after switching AWS accounts
cd infra/terraform/cluster
terraform init -backend-config=envs/backend-dev.hcl

terraform plan -var-file=envs/dev.tfvars -out=dev.tfplan
terraform apply dev.tfplan

# EKS control plane takes ~10-15 min to become ACTIVE -- apply
# finishing does not mean the API server is reachable yet.
$(terraform output -raw kubeconfig_command)
kubectl get nodes    # Auto Mode nodes join within a few minutes of the first pod being scheduled
```

Equivalently, `make ENV=dev terraform-init terraform-plan
terraform-apply` from the repo root does the same three steps.

Then deploy the app itself (Stage 12.2 delivers the Helm chart this
step references — not yet in the repo):

```bash
helm upgrade --install pvh-app infra/helm/pvh-app -f infra/helm/values/dev.yaml \
  --namespace pvh --create-namespace --atomic --timeout 10m --wait
```

## Tear down after the review window

```bash
terraform destroy -var-file=envs/dev.tfvars
```

This deletes the VPC and EKS cluster. It does **not** touch:
- ECR images (`bootstrap/`)
- The GitHub deploy role (`bootstrap/`)
- Weaviate Cloud / Qdrant Cloud data (external, per the Q3 decision)
- Aiven Postgres/Kafka data (external, pre-existing per ADR-009)

What you lose on every teardown, by design, since nothing here is
meant to be durable:
- Vault's data (it re-initializes fresh next `apply` — this is why
  Stage 12.4's KMS auto-unseal matters: without it, someone has to
  manually run `vault operator unseal` after every single cluster
  recreation, which defeats the point of an on-demand cluster)
- Keycloak's runtime state beyond what `infra/keycloak/realm.json`
  re-imports on boot (any users created ad hoc through the admin
  console beyond the seeded ones, active sessions, in-cluster audit
  history — Keycloak's own audit log, not `audit_logs` in Postgres,
  which is Aiven-hosted and survives)

If either of those losses stops being acceptable (e.g. this becomes an
always-on deployment instead of review-window), that's the signal to
revisit decision 1 in `../README.md`, not to patch around it here.

## What this does NOT set up yet

Ingress/TLS, the Helm chart itself, Weaviate Cloud/Qdrant Cloud
connection secrets, Vault's actual Helm release, and KEDA are Stages
12.2–12.6 — tracked in the project's Phase 12 plan, not silently
assumed here.
