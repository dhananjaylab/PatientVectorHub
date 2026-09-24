# infra/terraform/cluster/vpc.tf

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs             = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  cluster_name    = "pvh-${var.environment}"
  private_subnets = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i)]      # 10.60.0.0/20, 10.60.16.0/20, ...
  public_subnets  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i + 8)]  # 10.60.128.0/20, ...
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0" # verified current: 6.7.2 (Aug 2026)

  name = "pvh-${var.environment}"
  cidr = var.vpc_cidr

  azs             = local.azs
  private_subnets = local.private_subnets
  public_subnets  = local.public_subnets

  enable_nat_gateway   = true
  single_nat_gateway   = var.single_nat_gateway
  enable_dns_hostnames = true
  enable_dns_support   = true

  # EKS + AWS Load Balancer Controller subnet discovery tags. Auto Mode
  # and the ALB controller both rely on these rather than explicit
  # subnet IDs passed around by hand.
  public_subnet_tags = {
    "kubernetes.io/role/elb"                     = "1"
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"            = "1"
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
  }
}
