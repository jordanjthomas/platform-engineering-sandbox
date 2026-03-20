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
  endpoint_public_access = true
  # Private access keeps node-to-control-plane traffic within the VPC
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

# EKS add-ons — must be declared explicitly; not installed automatically by the module.
# vpc-cni initialises the CNI plugin on each node (required for NotReady → Ready transition).
# kube-proxy and coredns are required for cluster networking and DNS.
resource "aws_eks_addon" "vpc_cni" {
  cluster_name = module.eks.cluster_name
  addon_name   = "vpc-cni"
}

resource "aws_eks_addon" "kube_proxy" {
  cluster_name = module.eks.cluster_name
  addon_name   = "kube-proxy"
}

resource "aws_eks_addon" "coredns" {
  cluster_name = module.eks.cluster_name
  addon_name   = "coredns"
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
