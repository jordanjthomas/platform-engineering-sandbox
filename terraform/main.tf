module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project}-${var.environment}"
  cidr = var.vpc_cidr

  azs             = var.availability_zones
  public_subnets  = var.public_subnet_cidrs
  private_subnets = var.private_subnet_cidrs

  enable_nat_gateway     = var.enable_nat_gateway
  single_nat_gateway     = var.single_nat_gateway
  one_nat_gateway_per_az = var.one_nat_gateway_per_az

  enable_dns_hostnames = true
  enable_dns_support   = true

  # EKS requires these tags for the AWS Load Balancer Controller to auto-discover subnets when provisioning load balancers
  public_subnet_tags = {
    "kubernetes.io/role/elb"                    = "1"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"           = "1"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }
}

# VPC endpoints - allow nodes in private subnets to reach AWS APIs without traversing the NAT gateway.
# Interface endpoints: ec2 (VPC CNI ENI management), ecr.api/ecr.dkr (image pulls), sts (IRSA token
# exchange), logs (CloudWatch), ssm/ec2messages (SSM node access).
# Gateway endpoints: s3 (ECR image layers - free, no SG required).
#
# The security group restricts inbound 443 to the EKS node security group only (least privilege).
# Note: on a clean first apply, Terraform resolves this dependency correctly because the node security
# group is created as part of the EKS cluster setup, before the node group itself.

resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.project}-${var.environment}-vpc-endpoints"
  description = "Allow HTTPS inbound from EKS nodes to interface VPC endpoints"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "HTTPS from EKS nodes"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
}

locals {
  interface_endpoints = {
    ec2         = "com.amazonaws.${var.aws_region}.ec2"
    ecr_api     = "com.amazonaws.${var.aws_region}.ecr.api"
    ecr_dkr     = "com.amazonaws.${var.aws_region}.ecr.dkr"
    sts         = "com.amazonaws.${var.aws_region}.sts"
    logs        = "com.amazonaws.${var.aws_region}.logs"
    ssm         = "com.amazonaws.${var.aws_region}.ssm"
    ec2messages = "com.amazonaws.${var.aws_region}.ec2messages"
  }
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = module.vpc.vpc_id
  service_name        = each.value
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
}

# EKS cluster
## OIDC provider is created automatically by the module (v21+), enabling IRSA
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Public access required for CI/CD and local kubectl
  endpoint_public_access  = true
  # Private access keeps node-to-control-plane traffic within the VPC, avoiding NAT gateway
  endpoint_private_access = true

  # Grant the Terraform caller admin access to the cluster on creation
  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      min_size       = var.node_min_size
      max_size       = var.node_max_size
      desired_size   = var.node_desired_size
    }
  }
}

# ECR repository for app container images
resource "aws_ecr_repository" "app" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Secrets Manager
resource "aws_secretsmanager_secret" "app_api_key" {
  name                    = "/${var.environment}/${var.project}/admin-token"
  description             = "Bearer token required to call the namespace provisioner API - injected into the app via External Secrets Operator"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "app_api_key" {
  secret_id = aws_secretsmanager_secret.app_api_key.id
  secret_string = jsonencode({
    token = "PLACEHOLDER_VALUE"
  })
}
