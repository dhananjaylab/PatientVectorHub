# infra/terraform/ — two-stack layout

Phase 12 confirmed (Dhananjay, this session): build Terraform + Helm for
real AWS EKS, but **apply only for review windows and `terraform destroy`
after** rather than running a cluster continuously. That one decision is
why this is two separate root modules instead of one:

```
infra/terraform/
├── bootstrap/   # apply ONCE, essentially never destroyed
└── cluster/     # apply for a review window, destroy after
```

## Why split at all

Everything in `bootstrap/` has to outlive `cluster/`'s teardown, or the
ephemeral-cluster pattern breaks the first time you use it:

| If this lived in `cluster/` instead... | ...then `terraform destroy` would |
|---|---|
| The S3 state bucket | Delete the very state file `destroy` is reading from mid-run |
| ECR repositories | Delete every image `deploy.yml` built, forcing a full rebuild next review window |
| The GitHub Actions OIDC provider + deploy role | Break CI's `AWS_DEPLOY_ROLE` secret every cycle, needing manual re-wiring each time |

So `bootstrap/` holds exactly those three things and nothing else. It
has its own **local** Terraform state (there's a chicken-and-egg problem
in making the state bucket itself use a remote backend) — see
`bootstrap/README.md` for how Dhananjay keeps a copy of that state file
safe outside the ephemeral cluster's blast radius.

`cluster/` holds the VPC and EKS cluster — genuinely disposable, no
data lives in either (the two stateful services that could have lived
here, Weaviate and Qdrant, went to managed cloud instead — see the
Q3 decision below — specifically so nothing inside this ephemeral
cluster needs to survive a teardown).

## The three decisions this design is built on

Confirmed this session, before any of this code was written:

1. **EKS runs for review windows, not continuously** — `terraform
   apply` / `terraform destroy` on demand, not an always-on cluster.
   This is *why* the two-stack split exists at all.
2. **Vault stays self-hosted (BUSL), gets AWS KMS auto-unseal** — zero
   changes to `api-gateway/src/vault_client.py`'s existing Transit
   calls; the KMS key + Pod Identity association live in `cluster/`
   (Vault re-initializes fresh each cycle anyway, consistent with
   decision 1). OpenBao and AWS Secrets Manager were the alternatives
   considered — see the design writeup for why KMS auto-unseal won.
3. **Weaviate + Qdrant move to managed cloud** (Weaviate Cloud + Qdrant
   Cloud) — both are already fully env-configurable
   (`WEAVIATE_URL`/`QDRANT_URL`), and self-hosting either as a
   StatefulSet inside a cluster that gets destroyed every review window
   has nowhere durable to put the PVC. This follows directly from
   decision 1, not a separate cost preference.

## What's NOT verified

Nothing in `infra/terraform/` has been run through `terraform
init`/`validate`/`plan` against the real AWS/Terraform-Registry APIs —
this sandbox's network egress doesn't reach `registry.terraform.io`
or AWS. What *was* checked before anything here was written:

- Every `.tf` file parses as syntactically valid HCL (`python-hcl2`,
  see `tests/test_terraform_structure.py`).
- Module versions (`terraform-aws-modules/vpc ~> 6.0`,
  `terraform-aws-modules/eks ~> 21.0`, `hashicorp/aws ~> 6.0`) and the
  EKS Pod Identity / Auto Mode approach were checked against current
  (Sept 2026) documentation, not carried forward from older examples.
- The `pvh` single-namespace assumption in `pod_identity.tf` is
  checked against the actual committed
  `infra/k8s/network-policies/*.yaml` files, not the six-namespace
  layout the original brainstorm doc sketched (that doc was never what
  got built).

Run `terraform init && terraform validate` yourself before the first
real `apply` — that's the one verification step this session
genuinely cannot do on your behalf.
