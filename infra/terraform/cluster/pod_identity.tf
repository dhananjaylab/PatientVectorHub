# infra/terraform/cluster/pod_identity.tf
#
# This architecture needs very little pod-level AWS IAM: storage is
# Cloudflare R2, Postgres/Kafka are Aiven, vector stores/LLMs/embeddings
# are all external APIs -- none of that is AWS-IAM-shaped. The one
# confirmed need, from Q2 (Vault posture) in this Phase 12 design pass,
# is Vault's KMS auto-unseal: keep the existing self-hosted Vault
# (BUSL, zero application-code changes to vault_client.py's Transit
# calls) but stop it needing a manual `vault operator unseal` after
# every cluster recreation, since Vault runs inside this ephemeral
# cluster and gets torn down and reinitialized each review-window cycle.
#
# The KMS key + Pod Identity association are created here (Stage 12.1)
# because they're cluster-lifecycle infrastructure. The actual Vault
# Helm release, its `seal "awskms"` config stanza, and the Kubernetes
# auth method setup are Stage 12.4 -- deliberately not built yet.

resource "aws_kms_key" "vault_unseal" {
  description             = "PatientVectorHub Vault auto-unseal (${var.environment})"
  deletion_window_in_days = 7 # short window is fine -- a fresh Vault re-inits each cluster cycle anyway
  enable_key_rotation     = true
}

resource "aws_kms_alias" "vault_unseal" {
  name          = "alias/pvh-${var.environment}-vault-unseal"
  target_key_id = aws_kms_key.vault_unseal.key_id
}

data "aws_iam_policy_document" "vault_unseal" {
  statement {
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.vault_unseal.arn]
  }
}

resource "aws_iam_role" "vault_unseal" {
  name = "pvh-${var.environment}-vault-unseal"

  # EKS Pod Identity's trust policy is fixed and simple -- trusts the
  # pods.eks.amazonaws.com service principal, no per-cluster OIDC
  # provider or federation condition to maintain (that OIDC dance is
  # what IRSA required; Pod Identity replaces it).
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "pods.eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

resource "aws_iam_role_policy" "vault_unseal" {
  name   = "kms-auto-unseal"
  role   = aws_iam_role.vault_unseal.id
  policy = data.aws_iam_policy_document.vault_unseal.json
}

# Pending Stage 12.4 creating the `vault` ServiceAccount via the Helm
# chart -- association is written now so the IAM side is done.
# namespace = "pvh" is verified directly against every file in
# infra/k8s/network-policies/ (12-vault.yaml included): this repo uses
# one flat `pvh` namespace with app.kubernetes.io/name label selectors
# to distinguish components, not the six-namespace layout
# (pvh-app/pvh-ml/pvh-data/pvh-security/...) the original brainstorm doc
# sketched -- that doc was never what got built. service_account =
# "vault" is NOT yet verified the same way (no Helm chart exists to
# check against until Stage 12.2) -- it's the conventional default for
# a component labeled app.kubernetes.io/name: vault, kept consistent
# with that label. Stage 12.4 fixes this association's
# service_account value for real if the chart ends up naming it
# differently.
resource "aws_eks_pod_identity_association" "vault" {
  cluster_name    = module.eks.cluster_name
  namespace       = "pvh"
  service_account = "vault"
  role_arn        = aws_iam_role.vault_unseal.arn
}
