terraform {
  required_version = ">= 1.10.0"

  backend "s3" {
    # bucket, key, region, use_lockfile, and encrypt are injected at runtime
    # via -backend-config flags in CI (see .github/workflows/terraform.yml).
    # For local use, run:
    #   terraform init \
    #     -backend-config="bucket=<your-bucket>" \
    #     -backend-config="key=terraform.tfstate" \
    #     -backend-config="region=ap-southeast-2" \
    #     -backend-config="use_lockfile=true" \
    #     -backend-config="encrypt=true"
  }
}
