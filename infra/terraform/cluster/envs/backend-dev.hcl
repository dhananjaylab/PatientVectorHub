# infra/terraform/cluster/envs/backend-dev.hcl
#
# Usage: terraform init -backend-config=envs/backend-dev.hcl
# `bucket` = bootstrap/'s `tfstate_bucket` output. Region matches
# bootstrap/'s aws_region.

bucket = "REPLACE_ME" # terraform -chdir=../bootstrap output -raw tfstate_bucket
key    = "cluster/dev/terraform.tfstate"
region = "us-east-1"
