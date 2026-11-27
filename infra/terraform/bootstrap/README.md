# infra/terraform/bootstrap/

Apply this once per AWS account. Not part of the review-window
apply/destroy cycle — see `../README.md` for why.

## First apply

```bash
cd infra/terraform/bootstrap
terraform init                     # local backend -- see "State" below
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
```

Then wire the outputs into the two places that need them:

```bash
# 1. GitHub repo secret, so deploy.yml's role-to-assume resolves
terraform output -raw github_deploy_role_arn
# -> paste into: Settings -> Secrets and variables -> Actions -> AWS_DEPLOY_ROLE

# 2. cluster/'s tfvars and backend config
terraform output -raw github_deploy_role_arn    # -> cluster/envs/dev.tfvars
terraform output -raw github_deploy_role_name   # -> cluster/envs/dev.tfvars
terraform output -raw tfstate_bucket            # -> cluster/envs/backend-dev.hcl
```

## State

This stack's state is **local** (`terraform.tfstate` in this
directory), not S3 — it's the thing that *creates* the S3 bucket
`cluster/` uses, so it can't depend on that bucket existing yet.

Because there's no remote backend or locking here, treat this
directory's state file like a secret:

- It's already covered by the repo's `.gitignore` (`*.tfstate*`) —
  confirm before your first commit, don't assume.
- Keep a copy somewhere durable outside the repo (a private S3 object
  you upload by hand once, or a password manager attachment) so a
  wiped laptop doesn't mean re-importing every resource by hand.
- Only ever run `terraform apply`/`destroy` here from one machine at a
  time — there's no lock to stop two concurrent applies from
  corrupting each other.

## Destroying this stack

You almost never should. If you genuinely want to tear the whole AWS
footprint down (not just a review-window cluster):

```bash
# ECR repos hold real image history -- confirm you don't need it first
terraform destroy
```

Note `aws_s3_bucket.tfstate` has `lifecycle { prevent_destroy = true }`
— Terraform will refuse to delete it until that's removed by hand,
which is the point.
