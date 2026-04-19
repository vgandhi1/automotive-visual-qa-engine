#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Packaging Lambdas into ${ROOT}/dist (run terraform apply separately)."
mkdir -p "${ROOT}/dist"
for fn in edge_frame_processor anomaly_escalation vlm_orchestrator rework_router sap_integration; do
  zip -j "${ROOT}/dist/${fn}.zip" "${ROOT}/lambda/${fn}/index.py"
done
echo "Done. Terraform archive_file also builds zips under cloud/terraform/build on plan/apply."
