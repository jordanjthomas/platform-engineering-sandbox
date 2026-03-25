variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-southeast-2"
}

variable "environment" {
  description = "Deployment environment (e.g. sandbox, staging, prod)"
  type        = string
}

variable "project" {
  description = "Project name, used for resource naming and tagging"
  type        = string
}

variable "team" {
  description = "Owning team, used for resource tagging"
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name, used for subnet auto-discovery tags"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of AZs to deploy subnets into"
  type        = list(string)
  default     = ["ap-southeast-2a", "ap-southeast-2b", "ap-southeast-2c"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets, one per AZ"
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets, one per AZ"
  type        = list(string)
  default     = ["10.0.4.0/22", "10.0.8.0/22", "10.0.12.0/22"]
}

variable "enable_nat_gateway" {
  description = "Whether to provision a NAT Gateway for private subnets"
  type        = bool
}

variable "single_nat_gateway" {
  description = "Whether to use a single NAT Gateway for all AZs (true) or one per AZ (false)"
  type        = bool
}

variable "one_nat_gateway_per_az" {
  description = "Whether to provision one NAT Gateway per AZ (true) or a single shared NAT Gateway (false)"
  type        = bool
}

# EKS

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.35"
}

variable "node_instance_type" {
  description = "EC2 instance type for the EKS managed node group"
  type        = string
  default     = "t3.medium"
}

variable "node_desired_size" {
  description = "Desired number of nodes in the EKS managed node group"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of nodes in the EKS managed node group"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of nodes in the EKS managed node group"
  type        = number
  default     = 3
}

# ECR

variable "grafana_admin_password" {
  description = "Grafana admin password, supplied via TF_VAR_grafana_admin_password from GitHub Secrets"
  type        = string
  sensitive   = true
}

variable "ecr_repository_name" {
  description = "Name of the ECR repository for app container images"
  type        = string
}