environment  = "sandbox"
project      = "platform-engineering"
team         = "platform"
cluster_name = "platform-engineering-sandbox"

# AWS Configuration
aws_region = "ap-southeast-2"

# VPC Configuration
enable_nat_gateway     = true
single_nat_gateway     = true
one_nat_gateway_per_az = false
enable_dns_hostnames   = true
enable_dns_support     = true

# EKS Configuration
kubernetes_version = "1.35"
node_instance_type = "t3.medium"
node_desired_size  = 2
node_min_size      = 1
node_max_size      = 3

# ECR
ecr_repository_name = "platform-engineering-app"
