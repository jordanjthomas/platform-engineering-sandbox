# External Secrets Operator
resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = "2.2.0"
  namespace        = "external-secrets"
  create_namespace = true
  wait             = true
  timeout          = 600

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
  timeout          = 600
  disable_webhooks = true

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

# Kyverno policies -- deployed via the kyverno-policies chart to ensure policies
# are active before any workload Helm releases (loki, prometheus, etc.) are installed.
# Policy source of truth: terraform/policies/*.yaml (loaded via file())
resource "helm_release" "kyverno_policies" {
  name       = "kyverno-policies"
  repository = "https://kyverno.github.io/kyverno/"
  chart      = "kyverno-policies"
  version    = "3.3.4"
  namespace  = "kyverno"
  wait       = true
  timeout    = 600

  values = [yamlencode({
    podSecurityStandard = "privileged"
    customPolicies = [
      yamldecode(file("${path.root}/policies/deny-run-as-root.yaml")),
      yamldecode(file("${path.root}/policies/require-labels.yaml")),
      yamldecode(file("${path.root}/policies/require-resource-limits.yaml")),
    ]
  })]

  depends_on = [helm_release.kyverno]
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
  timeout          = 900

  values = [
    yamlencode({
      grafana = {
        adminPassword = var.grafana_admin_password
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

  depends_on = [module.eks, helm_release.kyverno_policies]
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
  timeout          = 600

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

  depends_on = [module.eks, helm_release.kyverno_policies]
}

# ClusterSecretStore -- configures how External Secrets Operator connects to AWS Secrets Manager.
# Used by the app ExternalSecret (applied via app-deploy workflow).
resource "kubectl_manifest" "cluster_secret_store" {
  yaml_body = yamlencode({
    apiVersion = "external-secrets.io/v1"
    kind       = "ClusterSecretStore"
    metadata = {
      name = "aws-secrets-manager"
    }
    spec = {
      provider = {
        aws = {
          service = "SecretsManager"
          region  = var.aws_region
        }
      }
    }
  })

  depends_on = [helm_release.external_secrets]
}

