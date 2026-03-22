# platform-engineering-sandbox

A platform API that lets teams self-serve Kubernetes namespaces without needing cluster access or knowing how to write resource manifests. A single API call provisions a namespace with sensible defaults: resource quotas, container limit ranges, network policies, and consistent labelling. This removes the platform team as a bottleneck for environment setup while enforcing guardrails that prevent resource sprawl and misconfiguration.

## Repo structure

```text
terraform/   - VPC, EKS cluster, ECR (IaC via Terraform)
app/         - FastAPI namespace provisioner API
k8s/         - Kubernetes manifests for deploying the API
.github/     - CI/CD workflows (Terraform + app deploy)
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

Three GitHub Actions workflows, all using OIDC (no stored AWS credentials):

**Terraform** (`terraform.yml`) — triggers on changes to `terraform/`:

- PR: fmt check, validate, plan, Infracost estimate, post summary as PR comment
- Merge to main: auto-apply to sandbox (with environment approval gate)

**App CI** (`app-ci.yml`) — triggers on PRs to `main` with changes to `app/`:

- Run tests (pytest with JUnit reporting)
- Build Docker image and run Trivy vulnerability scan

**App Deploy** (`app-deploy.yml`) — triggers on push to `main` with changes to `app/` or `k8s/`:

- Build Docker image and push to ECR (tagged with commit SHA)
- Deploy to sandbox EKS cluster (with environment approval gate)

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
