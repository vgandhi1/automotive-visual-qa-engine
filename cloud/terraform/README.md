# Terraform (AWS skeleton)

Creates S3, DynamoDB tables, SQS, Lambdas (Python 3.12 zip per `index.py`), Step Functions state machine, and an SQS → VLM orchestrator mapping.

## Usage

```bash
cd cloud/terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Set `sap_api_url` when you have a fixed HTTPS SAP mock or OData gateway endpoint (never pass unvalidated user input as a URL).

## Notes

- Lambda bundles are generated via `archive_file` into `build/` during plan/apply.
- Configure AWS credentials and region (`AWS_REGION` / `var.aws_region`) before apply.
