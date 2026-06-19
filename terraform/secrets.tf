# Secrets Manager entries for the two credentials the Lambda needs at runtime.
# Values come from variables (terraform.tfvars or CI secrets) — never hardcoded.

resource "aws_secretsmanager_secret" "tavily_api_key" {
  name        = "${var.project_name}/tavily-api-key"
  description = "Tavily API key used by the researcher step's web_search tool."
}

resource "aws_secretsmanager_secret_version" "tavily_api_key" {
  secret_id     = aws_secretsmanager_secret.tavily_api_key.id
  secret_string = var.tavily_api_key
}

resource "aws_secretsmanager_secret" "slack_bot_token" {
  name        = "${var.project_name}/slack-bot-token"
  description = "Slack bot token (chat:write scope) used by the vendored slack-poster MCP server."
}

resource "aws_secretsmanager_secret_version" "slack_bot_token" {
  secret_id     = aws_secretsmanager_secret.slack_bot_token.id
  secret_string = var.slack_bot_token
}
