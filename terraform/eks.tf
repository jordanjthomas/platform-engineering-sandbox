# EKS cluster
## OIDC provider is created automatically by the module (v21+)
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

  access_entries = {
    sso_admin = {
      principal_arn = var.sso_admin_role_arn
      policy_associations = {
        cluster_admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      min_size       = var.node_min_size
      max_size       = var.node_max_size
      desired_size   = var.node_desired_size
    }
  }
}

# EKS add-ons - must be declared explicitly; not installed automatically by the module.
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

resource "aws_eks_addon" "pod_identity_agent" {
  cluster_name = module.eks.cluster_name
  addon_name   = "eks-pod-identity-agent"
}

resource "aws_eks_addon" "ebs_csi_driver" {
  cluster_name             = module.eks.cluster_name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = aws_iam_role.ebs_csi_driver.arn

  depends_on = [aws_eks_addon.pod_identity_agent]
}

# gp3 StorageClass -- replaces the legacy gp2 in-tree provisioner with CSI-backed gp3.
# gp3 offers better baseline performance (3000 IOPS / 125 MiB/s) at lower cost than gp2.
resource "kubectl_manifest" "gp3_storage_class" {
  yaml_body = yamlencode({
    apiVersion = "storage.k8s.io/v1"
    kind       = "StorageClass"
    metadata = {
      name = "gp3"
      annotations = {
        "storageclass.kubernetes.io/is-default-class" = "true"
      }
    }
    provisioner       = "ebs.csi.aws.com"
    volumeBindingMode = "WaitForFirstConsumer"
    reclaimPolicy     = "Delete"
    parameters = {
      type      = "gp3"
      encrypted = "true"
    }
  })

  depends_on = [aws_eks_addon.ebs_csi_driver]
}
