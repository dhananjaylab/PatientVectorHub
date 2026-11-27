# infra/terraform/bootstrap/ecr.tf
#
# .github/workflows/deploy.yml already builds and pushes to
# $ECR/pvh-api:$GITHUB_SHA and $ECR/pvh-workers:$GITHUB_SHA -- these two
# repos are what makes that step succeed instead of erroring on a
# missing repository. Repos (and the images in them) live here in
# bootstrap/, not cluster/, so `terraform destroy` on an ephemeral
# review-window cluster never deletes built images.

locals {
  ecr_repos = ["pvh-api", "pvh-workers"]
}

resource "aws_ecr_repository" "this" {
  for_each = toset(local.ecr_repos)

  name                 = each.value
  image_tag_mutability = "IMMUTABLE" # a given :sha tag is never overwritten -- matches promotion-by-tag in deploy.yml

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.tfstate.arn
  }
}

resource "aws_ecr_lifecycle_policy" "expire_old" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last ${var.ecr_image_retention_count} tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["sha-", ""] # deploy.yml tags with $GITHUB_SHA (no prefix) -- tagPrefixList "" matches any tag
          countType     = "imageCountMoreThan"
          countNumber   = var.ecr_image_retention_count
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      }
    ]
  })
}
