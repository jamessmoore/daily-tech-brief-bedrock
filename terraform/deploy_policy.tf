# The IAM policy shared by the CI OIDC role and this project's dedicated
# local-deploy user -- previously managed entirely by hand via the AWS CLI
# (see CLAUDE.md: bumped ~6 times as real deploy/runtime gaps surfaced,
# most recently to add lambda:PutFunctionConcurrency). Bringing it under
# Terraform means future permission fixes go through a PR + merge like
# everything else, instead of an ad hoc `aws iam create-policy-version`.
#
# This resource was `terraform import`-ed against the policy that already
# existed from the original manual bootstrap (see README "GitHub Actions
# OIDC role") -- the OIDC provider, the trust policy on the CI role itself,
# and the CI role resource are intentionally left out of Terraform, since
# Terraform can't create the very role it needs to assume before it can run.

resource "aws_iam_policy" "deploy" {
  name = "${var.project_name}-deploy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "EcrRepo"
        Effect = "Allow"
        Action = [
          "ecr:CreateRepository",
          "ecr:DeleteRepository",
          "ecr:DescribeRepositories",
          "ecr:PutImageScanningConfiguration",
          "ecr:SetRepositoryPolicy",
          "ecr:GetRepositoryPolicy",
          "ecr:TagResource",
          "ecr:ListTagsForResource",
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage",
          "ecr:ListImages",
          "ecr:DescribeImages",
        ]
        Resource = "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.project_name}"
      },
      {
        Sid    = "IamRoles"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:GetRole",
          "iam:PutRolePolicy",
          "iam:GetRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
          "iam:ListRolePolicies",
          "iam:TagRole",
          "iam:ListInstanceProfilesForRole",
        ]
        Resource = [
          aws_iam_role.lambda.arn,
          aws_iam_role.scheduler.arn,
        ]
      },
      {
        Sid    = "IamPassRole"
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.lambda.arn,
          aws_iam_role.scheduler.arn,
        ]
      },
      {
        Sid    = "Lambda"
        Effect = "Allow"
        Action = [
          "lambda:CreateFunction",
          "lambda:DeleteFunction",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
          "lambda:ListVersionsByFunction",
          "lambda:TagResource",
          "lambda:ListTags",
          "lambda:GetPolicy",
          "lambda:InvokeFunction",
          "lambda:PutFunctionConcurrency",
          "lambda:DeleteFunctionConcurrency",
          "lambda:GetFunctionConcurrency",
        ]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}"
      },
      {
        Sid      = "LogsDescribe"
        Effect   = "Allow"
        Action   = "logs:DescribeLogGroups"
        Resource = "*"
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:DeleteLogGroup",
          "logs:PutRetentionPolicy",
          "logs:TagResource",
          "logs:ListTagsForResource",
          "logs:FilterLogEvents",
          "logs:GetLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}*"
      },
      {
        Sid    = "SecretsManager"
        Effect = "Allow"
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:DeleteSecret",
          "secretsmanager:DescribeSecret",
          "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecret",
          "secretsmanager:TagResource",
          "secretsmanager:GetSecretValue",
          "secretsmanager:GetResourcePolicy",
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/*"
      },
      {
        Sid    = "TerraformStateBucket"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket",
          "s3:PutBucketVersioning",
          "s3:GetBucketVersioning",
          "s3:PutEncryptionConfiguration",
          "s3:GetEncryptionConfiguration",
          "s3:PutBucketPublicAccessBlock",
          "s3:GetBucketPublicAccessBlock",
          "s3:ListBucket",
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}",
          "arn:aws:s3:::${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}/*",
        ]
      },
      {
        Sid    = "Scheduler"
        Effect = "Allow"
        Action = [
          "scheduler:CreateSchedule",
          "scheduler:DeleteSchedule",
          "scheduler:GetSchedule",
          "scheduler:UpdateSchedule",
          "scheduler:TagResource",
          "scheduler:ListTagsForResource",
        ]
        Resource = aws_scheduler_schedule.nightly_brief.arn
      },
      {
        # Lets Terraform (run either by CI or locally by the deploy user)
        # manage this policy's own versions going forward, instead of falling back
        # to a manual `aws iam create-policy-version` every time a new
        # permission gap turns up.
        Sid    = "SelfPolicyManagement"
        Effect = "Allow"
        Action = [
          "iam:GetPolicy",
          "iam:GetPolicyVersion",
          "iam:ListPolicyVersions",
          "iam:CreatePolicyVersion",
          "iam:DeletePolicyVersion",
        ]
        Resource = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.project_name}-deploy"
      },
      {
        Sid    = "SelfPolicyAttachment"
        Effect = "Allow"
        Action = [
          "iam:AttachUserPolicy",
          "iam:DetachUserPolicy",
          "iam:ListAttachedUserPolicies",
        ]
        Resource = aws_iam_user.deploy.arn
      },
      {
        Sid    = "CiRolePolicyAttachment"
        Effect = "Allow"
        Action = [
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
        ]
        Resource = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-github-deploy"
      },
    ]
  })
}

# Dedicated local-deploy user for this project, scoped to exactly the
# permissions in aws_iam_policy.deploy -- replaces the shared admin-group
# `flintstone` user, which had this policy attached directly on top of much
# broader access it didn't need for this project.
resource "aws_iam_user" "deploy" {
  name = "${var.project_name}-deploy"
}

resource "aws_iam_user_policy_attachment" "deploy_user" {
  user       = aws_iam_user.deploy.name
  policy_arn = aws_iam_policy.deploy.arn
}

resource "aws_iam_role_policy_attachment" "github_deploy" {
  role       = "${var.project_name}-github-deploy"
  policy_arn = aws_iam_policy.deploy.arn
}
