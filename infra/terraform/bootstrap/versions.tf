# infra/terraform/bootstrap/versions.tf
#
# Bootstrap has no remote backend of its own -- it's what CREATES the S3
# bucket the cluster/ stack later uses as its backend. State for this
# stack is local (terraform.tfstate, gitignored) plus a copy Dhananjay
# keeps outside the repo (S3 console, or a separate tiny bucket created
# by hand once). This is the standard chicken-and-egg answer for
# Terraform-managed remote state: one small stack has to bootstrap itself.

terraform {
  required_version = ">= 1.10.0" # S3 native state locking (use_lockfile) needs >= 1.10

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0" # verified current: 6.62.0 (Sept 2026)
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "PatientVectorHub"
      ManagedBy   = "terraform"
      Stack       = "bootstrap"
      Repo        = "dhananjaylab/PatientVectorHub"
    }
  }
}
