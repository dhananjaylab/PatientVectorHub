# infra/terraform/cluster/outputs.tf

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  value     = module.eks.cluster_certificate_authority_data
  sensitive = true
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnets
}

output "kubeconfig_command" {
  description = "Run this after apply, before any helm/kubectl command."
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.aws_region}"
}

output "vault_unseal_kms_key_arn" {
  description = "Feeds Stage 12.4's Vault `seal \"awskms\"` config stanza."
  value       = aws_kms_key.vault_unseal.arn
}
