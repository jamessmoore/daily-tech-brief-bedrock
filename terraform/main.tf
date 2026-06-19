terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

# --- ECR -----------------------------------------------------------------

resource "aws_ecr_repository" "this" {
  name                 = var.project_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- IAM: Lambda execution role -------------------------------------------

resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_bedrock_and_secrets" {
  name = "${var.project_name}-bedrock-secrets"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:Converse",
          "bedrock:ConverseStream",
        ]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}",
          "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_model_id}",
        ]
      },
      {
        Sid    = "SecretsRead"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          aws_secretsmanager_secret.tavily_api_key.arn,
          aws_secretsmanager_secret.slack_bot_token.arn,
        ]
      },
    ]
  })
}

# --- Lambda ----------------------------------------------------------------

resource "aws_lambda_function" "this" {
  function_name = var.project_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.this.repository_url}:latest"
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout

  environment {
    variables = {
      BEDROCK_MODEL_ID  = var.bedrock_model_id
      SLACK_CHANNEL     = var.slack_channel
      TAVILY_SECRET_ARN = aws_secretsmanager_secret.tavily_api_key.arn
      SLACK_SECRET_ARN  = aws_secretsmanager_secret.slack_bot_token.arn
    }
  }

  lifecycle {
    # CI pushes new images and calls `aws lambda update-function-code`
    # directly; terraform should not fight that by reverting image_uri.
    ignore_changes = [image_uri]
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}"
  retention_in_days = 14
}

# --- EventBridge Scheduler --------------------------------------------------

resource "aws_iam_role" "scheduler" {
  name = "${var.project_name}-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  name = "${var.project_name}-invoke-lambda"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.this.arn
    }]
  })
}

resource "aws_scheduler_schedule" "nightly_brief" {
  name                         = "${var.project_name}-nightly"
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.this.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
