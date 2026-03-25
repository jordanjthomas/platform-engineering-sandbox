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

# ECR repository for app container images
resource "aws_ecr_repository" "app" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# External Secrets Operator
resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = "2.2.0"
  namespace        = "external-secrets"
  create_namespace = true
  wait             = true

  depends_on = [module.eks]
}

# Kyverno - policy engine for Kubernetes admission control
resource "helm_release" "kyverno" {
  name             = "kyverno"
  repository       = "https://kyverno.github.io/kyverno/"
  chart            = "kyverno"
  version          = "3.3.4"
  namespace        = "kyverno"
  create_namespace = true
  wait             = true

  set {
    name  = "admissionController.replicas"
    value = "1"
  }

  set {
    name  = "admissionController.container.resources.limits.memory"
    value = "256Mi"
  }

  set {
    name  = "admissionController.container.resources.limits.cpu"
    value = "100m"
  }

  set {
    name  = "admissionController.container.resources.requests.memory"
    value = "128Mi"
  }

  set {
    name  = "admissionController.container.resources.requests.cpu"
    value = "100m"
  }

  depends_on = [module.eks]
}

# IAM role for External Secrets Operator (via EKS Pod Identity)
resource "aws_iam_role" "external_secrets" {
  name = "${var.cluster_name}-external-secrets"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "pods.eks.amazonaws.com"
        }
        Action = [
          "sts:AssumeRole",
          "sts:TagSession",
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "external_secrets" {
  name = "secrets-manager-read"
  role = aws_iam_role.external_secrets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = [
          aws_secretsmanager_secret.app_api_key.arn,
          aws_secretsmanager_secret.grafana_admin_password.arn,
        ]
      }
    ]
  })
}

resource "aws_eks_pod_identity_association" "external_secrets" {
  cluster_name    = module.eks.cluster_name
  namespace       = "external-secrets"
  service_account = "external-secrets"
  role_arn        = aws_iam_role.external_secrets.arn
}

# Secrets Manager
resource "aws_secretsmanager_secret" "app_api_key" {
  name                    = "/${var.environment}/${var.project}/admin-token"
  description             = "Bearer token required to call the namespace provisioner API - injected into the app via External Secrets Operator"
  recovery_window_in_days = 0
}

# Secret value is managed out-of-band to keep it out of Terraform state.
# See README.md "Secrets Management" for the seeding procedure.

# Grafana admin password - value managed out-of-band, same as admin-token above
resource "aws_secretsmanager_secret" "grafana_admin_password" {
  name                    = "/${var.environment}/${var.project}/grafana-admin-password"
  description             = "Grafana admin password - injected into Grafana via External Secrets Operator"
  recovery_window_in_days = 0
}

# kube-prometheus-stack - Prometheus, Grafana, AlertManager, node-exporter, kube-state-metrics
#
# Access Grafana UI:
#   kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
#   Credentials: admin / <value from Secrets Manager at /${environment}/${project}/grafana-admin-password>
#
# Access Prometheus UI:
#   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
#
# Access AlertManager UI:
#   kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093
#
# Future: expose via Ingress with ALB Ingress Controller for production use
resource "helm_release" "kube_prometheus_stack" {
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = "72.6.2"
  namespace        = "monitoring"
  create_namespace = true
  wait             = true
  timeout          = 600

  # Grafana - Loki datasource (must precede set blocks due to HCL attribute-before-block ordering)
  values = [
    yamlencode({
      grafana = {
        additionalDataSources = [
          {
            name      = "Loki"
            type      = "loki"
            url       = "http://loki.loki.svc.cluster.local:3100"
            access    = "proxy"
            isDefault = false
          }
        ]
      }
    })
  ]

  # Prometheus
  set {
    name  = "prometheus.prometheusSpec.retention"
    value = "7d"
  }

  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.accessModes[0]"
    value = "ReadWriteOnce"
  }

  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage"
    value = "10Gi"
  }

  # Note: EKS default StorageClass is gp2. If your cluster has a gp3 StorageClass, change this to "gp3".
  # Check available StorageClasses: kubectl get storageclass
  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName"
    value = "gp2"
  }

  set {
    name  = "prometheus.prometheusSpec.resources.requests.cpu"
    value = "200m"
  }

  set {
    name  = "prometheus.prometheusSpec.resources.requests.memory"
    value = "512Mi"
  }

  set {
    name  = "prometheus.prometheusSpec.resources.limits.cpu"
    value = "500m"
  }

  set {
    name  = "prometheus.prometheusSpec.resources.limits.memory"
    value = "1Gi"
  }

  # Grafana - admin credentials from Secrets Manager via ESO
  set {
    name  = "grafana.admin.existingSecret"
    value = "grafana-admin-credentials"
  }

  set {
    name  = "grafana.admin.userKey"
    value = "username"
  }

  set {
    name  = "grafana.admin.passwordKey"
    value = "password"
  }

  set {
    name  = "grafana.resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "grafana.resources.requests.memory"
    value = "128Mi"
  }

  set {
    name  = "grafana.resources.limits.cpu"
    value = "250m"
  }

  set {
    name  = "grafana.resources.limits.memory"
    value = "256Mi"
  }

  # AlertManager
  set {
    name  = "alertmanager.alertmanagerSpec.resources.requests.cpu"
    value = "50m"
  }

  set {
    name  = "alertmanager.alertmanagerSpec.resources.requests.memory"
    value = "64Mi"
  }

  set {
    name  = "alertmanager.alertmanagerSpec.resources.limits.cpu"
    value = "100m"
  }

  set {
    name  = "alertmanager.alertmanagerSpec.resources.limits.memory"
    value = "128Mi"
  }

  depends_on = [module.eks, helm_release.kyverno]
}

# loki-stack - Loki (log aggregation) + Promtail (log shipping)
# Loki is queried via the Grafana datasource configured in kube-prometheus-stack above
resource "helm_release" "loki_stack" {
  name             = "loki"
  repository       = "https://grafana.github.io/helm-charts"
  chart            = "loki-stack"
  version          = "2.10.2"
  namespace        = "loki"
  create_namespace = true
  wait             = true

  set {
    name  = "loki.persistence.enabled"
    value = "false"
  }

  set {
    name  = "loki.resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "loki.resources.requests.memory"
    value = "128Mi"
  }

  set {
    name  = "loki.resources.limits.cpu"
    value = "250m"
  }

  set {
    name  = "loki.resources.limits.memory"
    value = "256Mi"
  }

  set {
    name  = "promtail.enabled"
    value = "true"
  }

  set {
    name  = "promtail.resources.requests.cpu"
    value = "50m"
  }

  set {
    name  = "promtail.resources.requests.memory"
    value = "64Mi"
  }

  set {
    name  = "promtail.resources.limits.cpu"
    value = "100m"
  }

  set {
    name  = "promtail.resources.limits.memory"
    value = "128Mi"
  }

  depends_on = [module.eks]
}
