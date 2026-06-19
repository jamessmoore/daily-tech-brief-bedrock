variable "aws_region" {
  description = "AWS region to deploy into. Must have Bedrock access enabled for the chosen model."
  type        = string
  default     = "us-west-2"
}

variable "project_name" {
  description = "Name prefix used for the ECR repo, Lambda function, and related resources."
  type        = string
  default     = "daily-tech-brief-bedrock"
}

variable "bedrock_model_id" {
  description = <<-EOT
    Bedrock model ID (or cross-region inference profile ID) for Claude Sonnet 4.6.
    Find the exact value with:
      aws bedrock list-foundation-models --region <region> \
        --query "modelSummaries[?contains(modelId,'sonnet')].modelId"
    or, for cross-region inference profiles:
      aws bedrock list-inference-profiles --region <region>
  EOT
  type        = string
}

variable "lambda_memory_size" {
  description = "Lambda memory in MB. Tool-use loop + Node subprocess need headroom."
  type        = number
  default     = 1024
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 600
}

variable "schedule_expression" {
  description = "EventBridge Scheduler cron expression, evaluated in schedule_timezone."
  type        = string
  default     = "cron(0 2 * * ? *)"
}

variable "schedule_timezone" {
  description = "IANA timezone the schedule_expression is evaluated in."
  type        = string
  default     = "America/Phoenix"
}

variable "slack_channel" {
  description = "Slack channel the brief is posted to."
  type        = string
  default     = "#daily-brief"
}

variable "tavily_api_key" {
  description = "Tavily API key, supplied via terraform.tfvars (gitignored) or CI secret. Never committed."
  type        = string
  sensitive   = true
}

variable "slack_bot_token" {
  description = "Slack bot token for chat:write, supplied via terraform.tfvars (gitignored) or CI secret. Never committed."
  type        = string
  sensitive   = true
}
