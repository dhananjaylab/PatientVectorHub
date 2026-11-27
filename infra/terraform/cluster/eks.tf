# infra/terraform/cluster/eks.tf
#
# Auto Mode, not self-managed node groups: AWS owns node lifecycle,
# patching (weekly AMI refresh), OS hardening (Bottlerocket, immutable,
# no SSH), and the built-in NetworkPolicy enforcement engine. Chosen
# over classic managed node groups specifically because this cluster is
# stood up and torn down per review window (Dhananjay's Phase 12
# decision) -- there's no ongoing fleet to justify hand-tuning node
# groups, Karpenter, or AMI selection for. Verified current: EKS Auto
# Mode supports K8s up to 1.33 as of the terraform-aws-modules/eks v21
# release notes (Sept 2026).
#
# Identity: EKS Pod Identity, not IRSA. Verified current guidance (2026)
# is that Pod Identity is the default recommendation for new EC2-based
# clusters -- simpler trust policy, no per-cluster OIDC federation to
# wire up, and the Pod Identity agent is pre-installed on Auto Mode
# clusters (nothing to deploy separately). See pod_identity.tf.

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0" # verified current: 21.25.1 (Sept 18 2026)

  name               = local.cluster_name
  kubernetes_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  endpoint_public_access  = true # Dhananjay applies from his own machine, not a bastion
  endpoint_private_access = true

  compute_config = {
    enabled    = true
    node_pools = ["general-purpose"]
  }

  # Access Entries replace the old aws-auth ConfigMap (verified current
  # as the terraform-aws-modules/eks v21 default -- authentication_mode
  # defaults to API, not API_AND_CONFIG_MAP).
  enable_cluster_creator_admin_permissions = true

  access_entries = merge(
    {
      github_deploy = {
        principal_arn = var.github_deploy_role_arn
        policy_associations = {
          deploy = {
            # edit, not admin: this role builds+pushes images and runs
            # `helm upgrade`, it doesn't need to manage RBAC or delete
            # namespaces.
            policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
            access_scope = { type = "cluster" }
          }
        }
      }
    },
    {
      for arn in var.cluster_admin_arns : "admin-${md5(arn)}" => {
        principal_arn = arn
        policy_associations = {
          admin = {
            policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
            access_scope = { type = "cluster" }
          }
        }
      }
    }
  )
}
