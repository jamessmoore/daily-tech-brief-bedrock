output "ecr_repository_url" {
  description = "Push images here: docker push <this>:latest"
  value       = aws_ecr_repository.this.repository_url
}

output "lambda_function_name" {
  value = aws_lambda_function.this.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.this.arn
}

output "scheduler_name" {
  value = aws_scheduler_schedule.nightly_brief.name
}
