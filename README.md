# platform-engineering-sandbox

A platform API that lets teams self-serve Kubernetes namespaces without needing cluster access or knowing how to write resource manifests. A single API call provisions a namespace with sensible defaults: resource quotas, container limit ranges, network policies, and consistent labelling. This removes the platform team as a bottleneck for environment setup while enforcing guardrails that prevent resource sprawl and misconfiguration.

## Repo structure

```text
terraform/           - VPC, EKS cluster, ECR, Pod Identity, IAM, Helm releases (IaC via Terraform)
app/                 - FastAPI namespace provisioner API
k8s/app/             - Kubernetes manifests for deploying the API (Kustomize-managed)
k8s/external-secrets/- ExternalSecret for app secrets
k8s/monitoring/      - ServiceMonitor, PrometheusRule, Grafana dashboard
k8s/namespace/       - Namespace definition
.github/             - CI/CD workflows (Terraform + app deploy)
```

## Infrastructure

Terraform provisions a VPC, EKS cluster, and ECR repository in `ap-southeast-2`.

## API

All endpoints except `/healthz` and `/metrics` require `Authorization: Bearer <token>`.

| Method   | Path                 | Description                           |
| -------- | -------------------- | ------------------------------------- |
| `POST`   | `/namespaces`        | Provision a namespace with guardrails |
| `GET`    | `/namespaces`        | List managed namespaces               |
| `GET`    | `/namespaces/{name}` | Get namespace details + quota usage   |
| `DELETE` | `/namespaces/{name}` | Delete a managed namespace            |
| `GET`    | `/healthz`           | Health check                          |
| `GET`    | `/metrics`           | Prometheus metrics                    |

## Local development

```bash
cd app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## CI/CD

GitHub Actions workflows, all using OIDC (no stored AWS credentials):

**Terraform Plan** (`terraform-plan.yml`) -- triggers on PRs with changes to `terraform/`:

- fmt check, validate, plan, Infracost estimate, post summary as PR comment

**Terraform Apply** (`terraform-apply.yml`) -- triggers on push to `main` with changes to `terraform/`:

- Auto-apply to sandbox (with environment approval gate)

**Terraform Destroy** (`terraform-destroy.yml`) -- manual trigger only (`workflow_dispatch`)

**App CI** (`app-ci.yml`) -- triggers on PRs to `main` with changes to `app/` or `k8s/`, or manual trigger:

- Run tests (pytest with JUnit reporting)
- Build Docker image and run Trivy vulnerability scan

**App Deploy** (`app-deploy.yml`) -- triggers on push to `main` with changes to `app/` or `k8s/`, or manual trigger:

- Build Docker image and push to ECR (tagged with commit SHA)
- Deploy to sandbox EKS cluster (with environment approval gate)

## Deployment order

Infrastructure and the application are deployed by separate workflows with no automatic dependency between them. On a fresh deploy (or after a full teardown), follow this order:

1. **Configure GitHub repo secrets** -- the following secrets must be set before running any workflow:

   | Secret | Description |
   | ------ | ----------- |
   | `AWS_ROLE_ARN` | OIDC role ARN for GitHub Actions |
   | `TF_STATE_BUCKET` | S3 bucket for Terraform state |
   | `GRAFANA_ADMIN_PASSWORD` | Grafana admin password |
   | `SSO_ADMIN_ROLE_ARN` | AWS SSO admin role ARN for EKS cluster access |
   | `INFRACOST_API_KEY` | Infracost API key (used by plan workflow) |

2. **Terraform Apply** -- push changes to `terraform/` or trigger manually. Wait for the workflow to complete. This provisions the VPC, EKS cluster, ECR, ESO, Kyverno, IAM, kube-prometheus-stack, and loki-stack.
3. **Seed app secret** -- Terraform creates the Secrets Manager secret for the app admin token but not its value (kept out of state). Set it once after the initial apply:

   ```bash
   aws secretsmanager put-secret-value \
     --secret-id /sandbox/platform-engineering/admin-token \
     --secret-string '{"token":"<your-actual-token>"}' \
     --region ap-southeast-2
   ```

4. **App Deploy** -- push changes to `app/` or `k8s/`, or trigger manually from the Actions tab. This builds the container image, pushes to ECR, and applies the Kubernetes manifests (including monitoring resources when CRDs are present).

For day-to-day changes, pushes to `terraform/` or `app/`/`k8s/` trigger their respective workflows automatically and can run independently.

## Secrets management

Secrets follow two patterns depending on the consumer:

**Platform secrets** (Grafana admin password, SSO role ARN) are passed directly to Terraform via `TF_VAR_` environment variables sourced from GitHub repo secrets. This avoids circular dependencies between Terraform resources and keeps the deployment to a single `terraform apply`.

**Application secrets** (API admin token) are stored in AWS Secrets Manager and synced into Kubernetes via [External Secrets Operator](https://external-secrets.io/) (ESO). The ESO controller authenticates to AWS using EKS Pod Identity, so no static credentials or OIDC trust policy boilerplate is required.

### How ESO works (app secrets)

1. **Terraform** provisions the Secrets Manager secret (the container), installs ESO via Helm, the Pod Identity agent addon, an IAM role scoped to read the secret, a Pod Identity association binding that role to the ESO service account, and a `ClusterSecretStore` pointing at Secrets Manager
2. **App Deploy** applies an `ExternalSecret` that syncs the secret value into a native Kubernetes Secret
3. **The app** reads the Kubernetes Secret as an environment variable. It has no awareness of Secrets Manager

### Seeding the app secret

Terraform creates the Secrets Manager secret but does not manage the value, keeping it out of state. Set the value out-of-band after the initial `terraform apply`:

```bash
aws secretsmanager put-secret-value \
  --secret-id /sandbox/platform-engineering/admin-token \
  --secret-string '{"token":"<your-actual-token>"}' \
  --region ap-southeast-2
```

To rotate the value, run the same command with the new token. ESO will pick up the change within the `refreshInterval` configured on the ExternalSecret (default: 1h).

### Verifying the sync

After deploying, confirm the ExternalSecret is healthy:

```bash
kubectl get externalsecret namespace-provisioner-token -n platform
```

The `STATUS` column should show `SecretSynced`. If it shows an error, check the ESO controller logs:

```bash
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets
```

## Observability

The cluster runs a full observability stack deployed via Terraform Helm releases:

- **Prometheus** (kube-prometheus-stack) -- metrics collection, alerting, node-exporter, kube-state-metrics
- **Grafana** -- dashboards and log exploration
- **AlertManager** -- alert routing
- **Loki + Promtail** (loki-stack) -- log aggregation from all pods

### Accessing the UIs

All observability UIs are cluster-internal only (no Ingress). Access via port-forward:

```bash
# Grafana (dashboards, logs)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80

# Prometheus (targets, query)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090

# AlertManager (alert status)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093
```

Grafana admin password is supplied via the `GRAFANA_ADMIN_PASSWORD` GitHub repo secret and passed directly to the kube-prometheus-stack Helm release at deploy time. The default username is `admin`.

### App metrics

The namespace provisioner exposes Prometheus metrics at `/metrics`. A ServiceMonitor in the `platform` namespace configures Prometheus to scrape it every 30 seconds.

Custom metrics:

- `namespace_provisioner_requests_total{method, path, status}` -- request counter
- `namespace_provisioner_request_duration_seconds{method, path}` -- request latency histogram

A "Namespace Provisioner Overview" Grafana dashboard is auto-provisioned via a ConfigMap, showing request rate, error rate, latency percentiles (p50/p95/p99), pod restarts, CPU/memory usage, and recent logs from Loki.

### Alerts

Two PrometheusRule alerts are configured:

| Alert | Condition | Severity |
| ----- | --------- | -------- |
| HighErrorRate | 5xx rate > 5% for 5 minutes | warning |
| FrequentPodRestarts | > 3 restarts in 10 minutes | critical |

View alert status in AlertManager or in the Prometheus UI under Alerts.

## Cluster access

EKS access entries are managed in Terraform (`terraform/eks.tf`). Two principals have cluster admin access:

- **CI/CD role** -- the GitHub Actions OIDC role, granted automatically via `enable_cluster_creator_admin_permissions`
- **SSO admin role** -- your AWS SSO administrator role, added via the `access_entries` block using the `SSO_ADMIN_ROLE_ARN` GitHub secret

To access the cluster locally:

```bash
aws sso login
aws eks update-kubeconfig --name platform-engineering-sandbox --region ap-southeast-2
kubectl get nodes
```

## Network architecture

The API is deployed as a `ClusterIP` service, so it is only reachable from within the cluster network. There is no Ingress, LoadBalancer, or other external route.

I kept this cluster-internal deliberately. This is a sandbox project, and the namespace-provisioner is a control-plane API that creates and deletes cluster resources (namespaces, ResourceQuotas, NetworkPolicies). Exposing it externally would mean standing up an ingress controller, TLS, and a proper auth layer (OAuth2/OIDC), which is more infrastructure than I need right now. The simple bearer-token auth works fine as a second layer internally, but I wouldn't want it as the only thing between the internet and namespace deletion.

For now, access from outside the cluster goes through `kubectl port-forward`, which tunnels through the Kubernetes API server using existing cluster credentials.

> If I want to expose this externally later, the path would be: AWS Load Balancer Controller, an Ingress resource with TLS via ACM, and an authN/authZ layer in front (e.g. OAuth2 proxy).

## Usage

Port-forward to access the API from your machine:

```bash
kubectl port-forward svc/namespace-provisioner -n platform 8080:80
```

Create a namespace:

```bash
curl -X POST http://localhost:8080/namespaces \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "payments-dev", "team": "payments", "environment": "dev"}'
```

Override quota defaults:

```bash
curl -X POST http://localhost:8080/namespaces \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "ml-dev", "team": "ml", "environment": "dev", "quota": {"cpu_limits": "8", "memory_limits": "16Gi", "pods": 50}}'
```

List managed namespaces (with optional filters):

```bash
curl http://localhost:8080/namespaces?team=payments \
  -H "Authorization: Bearer <token>"
```

Get namespace details and live quota usage:

```bash
curl http://localhost:8080/namespaces/payments-dev \
  -H "Authorization: Bearer <token>"
```

Delete a namespace (rejects if pods are running, use `?force=true` to override):

```bash
curl -X DELETE http://localhost:8080/namespaces/payments-dev \
  -H "Authorization: Bearer <token>"
```
