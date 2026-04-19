# Visual Quality Inspection & Rework Routing Engine

End-to-end reference implementation for the architecture described in [plan.md](plan.md): edge CLIP inspection on NVIDIA Jetson (or CPU dev mode), AWS serverless path (IoT → Lambda → SQS → VLM stub → Step Functions → SAP mock), and an MES-style FastAPI service.

## Repository layout

- `edge/` — camera capture, CLIP inference, CLIP patch-saliency anomaly crop, MQTT publisher, SQLite offline queue, orchestration
- `cloud/lambda/` — AWS Lambda handlers (frame processor, anomaly escalation, VLM orchestrator, rework router, SAP integration)
- `cloud/terraform/` — IaC skeleton (S3, DynamoDB, SQS, Lambdas, IoT policy placeholder)
- `cloud/mes_service/` — FastAPI service for defect/pass logging (DynamoDB + optional SNS when configured)
- `mlops/` — latency benchmarking and evaluation stubs
- `tests/` — integration tests with fixtures

## Quick start (development, no Jetson)

```bash
cd edge
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py --config config.yaml --synthetic --max-frames 5 --mqtt-offline-only
```

First run downloads `openai/clip-vit-base-patch32` weights via Hugging Face.

## Tests (from repo root)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pytest pyyaml httpx fastapi uvicorn pydantic boto3
cd edge && pytest -m "not slow" -q
cd ../cloud/mes_service && pytest -q
cd ../.. && pytest -q tests/integration_test.py
```

## Quick start (AWS)

See [plan.md](plan.md) section 10 and `cloud/terraform/README.md` for `terraform init/apply` and `cloud/deploy_all.sh`.

## Security

- Do not commit IoT certificates or API tokens; use environment variables and AWS Secrets Manager in production.
- Lambdas and the MES service avoid logging raw payloads that may contain sensitive fields; use correlation IDs.

## License

Apache 2.0 — see [LICENSE](LICENSE).
