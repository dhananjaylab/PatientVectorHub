# infra/terraform/cluster/versions.tf
#
# This stack is the ephemeral half of the two-stack split -- applied for
# a review window, destroyed after. See ../README.md for why it's split
# from bootstrap/ this way, and README.md in this directory for the
# actual apply/destroy commands.

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0" # verified current: 6.62.0 (Sept 2026), same line as bootstrap/
    }
  }

  backend "s3" {
    # bucket/key/region are supplied at `terraform init -backend-config=...`
    # time (see envs/backend-<env>.hcl) because a backend block cannot
    # reference variables or bootstrap/'s outputs directly -- Terraform
    # needs the backend resolved before it can even read state. This is
    # a real Terraform limitation, not an oversight here.
    use_lockfile = true # S3 native locking (TF >= 1.10) -- no DynamoDB table to provision or destroy
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "PatientVectorHub"
      ManagedBy   = "terraform"
      Stack       = "cluster"
      Environment = var.environment
      Repo        = "dhananjaylab/PatientVectorHub"
    }
  }
}
