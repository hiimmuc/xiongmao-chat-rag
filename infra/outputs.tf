output "acm_validation_record" {
  description = "Step 2 of docs/deploy-aws.md: add this CNAME in Cloudflare (DNS only) so the frontend certificate can be issued."
  value = [for o in aws_acm_certificate.frontend.domain_validation_options : {
    type    = o.resource_record_type
    name    = o.resource_record_name
    content = o.resource_record_value
  }]
}

output "cloudflare_dns_records" {
  description = "Step 4 of docs/deploy-aws.md: add these in Cloudflare. Proxy status must be DNS only (grey cloud)."
  value = [
    { type = "CNAME", name = var.domain, content = aws_cloudfront_distribution.frontend.domain_name },
    { type = "A", name = var.api_domain, content = aws_eip.server.public_ip },
  ]
}

output "github_variables" {
  description = "Step 6 of docs/deploy-aws.md: GitHub repository variables (Settings > Secrets and variables > Actions > Variables). None are secret."
  value = {
    AWS_REGION                 = var.region
    AWS_DEPLOY_ROLE_ARN        = aws_iam_role.deploy.arn
    ECR_REPOSITORY_URL         = aws_ecr_repository.api.repository_url
    DEPLOY_BUCKET              = aws_s3_bucket.deploy.bucket
    FRONTEND_BUCKET            = aws_s3_bucket.frontend.bucket
    CLOUDFRONT_DISTRIBUTION_ID = aws_cloudfront_distribution.frontend.id
    SERVER_NAME                = local.server_name
    VITE_API_URL               = "https://${var.api_domain}/api/v1"
  }
}

output "parameter_path" {
  description = "Step 5 of docs/deploy-aws.md: put the secrets under this SSM path."
  value       = local.parameter_path
}

output "server_instance_id" {
  description = "Open a shell with: aws ssm start-session --target <id>"
  value       = aws_instance.server.id
}
