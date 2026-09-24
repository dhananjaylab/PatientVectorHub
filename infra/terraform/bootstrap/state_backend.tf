# infra/terraform/bootstrap/state_backend.tf
#
# Holds cluster/'s remote state. This bucket survives every
# `terraform destroy` run against cluster/ -- that's the entire point of
# the two-stack split (see infra/terraform/README.md). Versioned so a
# bad `apply` can be recovered from; SSE-KMS with a dedicated key rather
# than the default AWS-managed S3 key, since Terraform state can contain
# sensitive values (Aiven connection strings, etc. -- anything not
# already routed through Vault/Secrets Manager).

resource "aws_kms_key" "tfstate" {
  description             = "PatientVectorHub Terraform state encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "tfstate" {
  name          = "alias/pvh-tfstate"
  target_key_id = aws_kms_key.tfstate.key_id
}

resource "aws_s3_bucket" "tfstate" {
  bucket = "pvh-terraform-state-${data.aws_caller_identity.current.account_id}"

  # Guards against `terraform destroy` in bootstrap/ accidentally taking
  # the state bucket (and therefore cluster/'s state) with it.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.tfstate.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Note: no aws_dynamodb_table here. Terraform >= 1.10's S3 backend
# supports native locking (`use_lockfile = true`) via a lock file
# written alongside the state object -- verified current as of the
# 1.10 release notes, replacing the old DynamoDB-table pattern. One
# fewer resource to provision, bill for, and keep in sync.

data "aws_caller_identity" "current" {}
