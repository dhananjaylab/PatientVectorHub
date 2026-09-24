# infra/terraform/bootstrap/variables.tf

variable "aws_region" {
  description = "AWS region for the state bucket, ECR repos, and OIDC role."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "GitHub owner/repo allowed to assume the deploy role via OIDC."
  type        = string
  default     = "dhananjaylab/PatientVectorHub"
}

variable "github_environments" {
  description = <<-EOT
    GitHub Environment names deploy.yml gates on. The OIDC trust policy
    only allows tokens whose `environment` claim matches one of these --
    a PR from a fork, or a push to an arbitrary branch with no
    environment, cannot assume the role even if the repo name matches.
  EOT
  type        = list(string)
  default     = ["dev", "staging", "production"]
}

variable "ecr_image_retention_count" {
  description = "How many tagged images to keep per ECR repo before older ones expire (cost control, not security)."
  type        = number
  default     = 15
}
