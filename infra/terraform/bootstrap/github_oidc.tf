# infra/terraform/bootstrap/github_oidc.tf
#
# .github/workflows/deploy.yml already has:
#   - uses: aws-actions/configure-aws-credentials@v4
#     with: { role-to-assume: "${{ secrets.AWS_DEPLOY_ROLE }}", aws-region: us-east-1 }
# That secret has nothing to point at yet -- this file creates the role
# and the trust relationship, and this stack's output prints the ARN to
# put in the repo's AWS_DEPLOY_ROLE secret.
#
# Thumbprint is fetched live (data.tls_certificate) rather than
# hardcoded -- AWS's own guidance notes GitHub's intermediate CA cert
# rotates, so a value copy-pasted from a blog post goes stale silently.

data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]
}

# Trust policy: only workflow runs for this exact repo, deploying
# through one of the named GitHub Environments (dev/staging/production),
# may assume this role. A fork's PR, or a push with no environment
# gate, cannot -- the `environment:` claim only appears in the OIDC
# token when a job declares `environment:`, which every deploy job in
# deploy.yml already does.
data "aws_iam_policy_document" "deploy_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for env in var.github_environments : "repo:${var.github_repo}:environment:${env}"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "pvh-github-actions-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_trust.json
  max_session_duration = 3600
}

# Deliberately scoped, not AdministratorAccess: ECR push/pull for the
# two repos above, plus enough EKS/describe access for
# `aws eks update-kubeconfig` and `helm upgrade` to work against a
# cluster that cluster/ created. It does NOT include eks:CreateCluster,
# ec2:*, or iam:* -- Terraform applies for cluster/ run from Dhananjay's
# own credentials (or a separate, more privileged CI role), not this
# one. This role is for image push + Helm deploy only.
data "aws_iam_policy_document" "deploy_permissions" {
  statement {
    sid    = "EcrAuth"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"] # GetAuthorizationToken does not support resource-level scoping
  }

  statement {
    sid    = "EcrPushPull"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = [for r in aws_ecr_repository.this : r.arn]
  }

  statement {
    sid    = "EksDescribeForKubeconfig"
    effect = "Allow"
    actions = [
      "eks:DescribeCluster",
      "eks:ListClusters",
    ]
    resources = ["arn:aws:eks:${var.aws_region}:${data.aws_caller_identity.current.account_id}:cluster/pvh-*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "pvh-github-actions-deploy-permissions"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.deploy_permissions.json
}
