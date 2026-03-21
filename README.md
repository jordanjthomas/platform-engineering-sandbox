# platform-engineering-sandbox

Self-service Kubernetes namespace provisioner running on EKS. Provisions namespaces with ResourceQuota, LimitRange, NetworkPolicy, and consistent labelling via a FastAPI HTTP API.

## Repo structure

```text
terraform/   — VPC, EKS cluster, ECR (IaC via Terraform)
app/         — FastAPI namespace provisioner API
k8s/         — Kubernetes manifests for deploying the API
.github/     — CI/CD workflows (Terraform + app deploy)
```

## Infrastructure

Terraform provisions a VPC, EKS cluster, and ECR repository in `ap-southeast-2`.

```bash
cd terraform
terraform init -backend-config="bucket=<state-bucket>" -backend-config="key=sandbox/terraform.tfstate" -backend-config="region=ap-southeast-2"
terraform plan -var-file="config/sandbox.tfvars"
```

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

## Deploy

Push to `main` with changes under `app/` or `k8s/` triggers the app deploy workflow: test, build, push to ECR, deploy to the sandbox EKS cluster.
