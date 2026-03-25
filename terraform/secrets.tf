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
  description             = "Grafana admin password - passed directly to the kube-prometheus-stack Helm release"
  recovery_window_in_days = 0
}

data "aws_secretsmanager_secret_version" "grafana_admin_password" {
  secret_id = aws_secretsmanager_secret.grafana_admin_password.id
}
