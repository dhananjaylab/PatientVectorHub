# infra/terraform/cluster/variables.tf

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  description = "dev | staging | production -- matches the GitHub Environment name and prod.yaml/dev.yaml's naming."
  type        = string
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment must be dev, staging, or production."
  }
}

variable "kubernetes_version" {
  description = "Verified current EKS-supported version as of Sept 2026."
  type        = string
  default     = "1.33"
}

variable "vpc_cidr" {
  type    = string
  default = "10.60.0.0/16"
}

variable "az_count" {
  description = <<-EOT
    EKS requires subnets across >= 2 AZs. Kept at 2 (not 3) to control
    NAT/ENI cost on a cluster that's only up for review windows --
    revisit if this ever becomes an always-on deployment.
  EOT
  type        = number
  default     = 2
}

variable "single_nat_gateway" {
  description = "One NAT for the whole VPC instead of one per AZ -- the standard cost/HA tradeoff for a non-always-on cluster."
  type        = bool
  default     = true
}

# ── Values that come from `terraform output` in bootstrap/ ──────────
# Not read automatically (bootstrap/ and cluster/ are deliberately
# separate state files with no remote_state data source between them,
# so destroying cluster/ can never touch bootstrap/'s resources even by
# accident of a broken dependency graph). Pass explicitly via tfvars,
# copied from `terraform -chdir=../bootstrap output`.

variable "github_deploy_role_arn" {
  description = "bootstrap/ output: github_deploy_role_arn"
  type        = string
}

variable "github_deploy_role_name" {
  description = "bootstrap/ output: github_deploy_role_name"
  type        = string
}

variable "cluster_admin_arns" {
  description = "IAM users/roles (e.g. Dhananjay's own IAM user ARN) granted the EKS ClusterAdmin access policy, in addition to whoever runs `terraform apply` (which gets it automatically)."
  type        = list(string)
  default     = []
}
