output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = module.vpc.vpc_cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = module.vpc.public_subnets
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = module.vpc.private_subnets
}

output "nat_gateway_public_ips" {
  description = "Public IPs of the NAT gateway(s)"
  value       = module.vpc.nat_public_ips
}

# EKS

output "eks_cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Endpoint URL of the EKS cluster API server"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_certificate_authority_data" {
  description = "Base64-encoded certificate authority data for the EKS cluster"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "eks_cluster_oidc_issuer_url" {
  description = "OIDC issuer URL for the EKS cluster — used to configure IRSA trust policies"
  value       = module.eks.cluster_oidc_issuer_url
}

# ECR

output "ecr_repository_url" {
  description = "URI of the ECR repository (use as the image base URL in manifests)"
  value       = aws_ecr_repository.app.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of the ECR repository"
  value       = aws_ecr_repository.app.arn
}

# Secrets Manager

output "app_secret_arn" {
  description = "ARN of the app API key secret in Secrets Manager"
  value       = aws_secretsmanager_secret.app_api_key.arn
}

output "app_secret_name" {
  description = "Name of the app API key secret in Secrets Manager (use in External Secrets manifests)"
  value       = aws_secretsmanager_secret.app_api_key.name
}
