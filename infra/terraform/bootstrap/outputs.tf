# infra/terraform/bootstrap/outputs.tf

output "tfstate_bucket" {
  description = "Pass this to cluster/'s backend-<env>.hcl as `bucket`."
  value       = aws_s3_bucket.tfstate.id
}

output "tfstate_kms_key_arn" {
  value = aws_kms_key.tfstate.arn
}

output "ecr_repository_urls" {
  description = "For the $ECR variable in deploy.yml (drop the trailing /pvh-api or /pvh-workers)."
  value       = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}

output "github_deploy_role_arn" {
  description = "Put this in the repo's AWS_DEPLOY_ROLE secret (Settings -> Secrets and variables -> Actions)."
  value       = aws_iam_role.github_deploy.arn
}

output "github_deploy_role_name" {
  description = "Needed by cluster/'s EKS access entry so this role can actually run kubectl/helm against the cluster, not just call the AWS API."
  value       = aws_iam_role.github_deploy.name
}
