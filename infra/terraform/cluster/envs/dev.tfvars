# infra/terraform/cluster/envs/dev.tfvars
#
# Copy of the two role outputs from bootstrap/ -- run
#   terraform -chdir=../bootstrap output -raw github_deploy_role_arn
#   terraform -chdir=../bootstrap output -raw github_deploy_role_name
# after bootstrap/ has been applied once, and paste the results below.
# (Not read automatically -- see the comment in variables.tf on why
# these two stacks don't share a remote_state data source.)

environment = "dev"
aws_region  = "us-east-1"

github_deploy_role_arn  = "REPLACE_ME" # terraform -chdir=../bootstrap output -raw github_deploy_role_arn
github_deploy_role_name = "REPLACE_ME" # terraform -chdir=../bootstrap output -raw github_deploy_role_name

# Add your own IAM user/role ARN here to get kubectl/Helm access without
# re-running `terraform apply` every session -- cluster-creator gets
# admin automatically, but that's only whoever ran `apply`.
cluster_admin_arns = []

# Cheapest viable topology for a review-window cluster.
az_count           = 2
single_nat_gateway = true
