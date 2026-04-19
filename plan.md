# Visual Quality Inspection & Rework Routing Engine
## A Next-Generation Automotive Defect Detection & ERP Integration System

**Project Status:** Specification & Build Plan  
**Target Timeline:** 9 weeks  
**Hardware:** NVIDIA Jetson Nano 2GB, USB 3.0 UVC Camera  
**Cloud:** AWS (IoT Core, SageMaker, Lambda, Step Functions, S3)  
**ERP Integration:** SAP (S/4HANA OData API or mock endpoint)

---

## 1. Project Vision & Problem Statement

### The Problem
In automotive manufacturing (EV/traditional), post-weld and post-paint quality inspections rely on human inspectors who must:
1. Manually identify defects
2. Describe them in natural language (subjective, time-consuming)
3. Route vehicles to the correct rework station (paint touch-up, weld rework, body shop)
4. Log rework tickets into the ERP system

This process introduces latency, subjectivity, inconsistency, and operator fatigue.

### The Solution
An automated **Visual Quality Inspection & Rework Routing Engine** that:
- Runs high-speed anomaly detection on Jetson Nano edge hardware
- Escalates ambiguous detections to a cloud VLM for structured analysis
- Automatically generates standardized rework tickets with repair action recommendations
- Routes vehicles to the correct rework station via SAP ERP integration
- Maintains full traceability (VIN, location, defect description, repair action)

### Success Metrics
| Metric | Baseline | Target |
|---|---|---|
| Inspection cycle time | 45–60s (manual) | <3s (automated) |
| Defect escape rate | 2–3% | <0.5% |
| Rework ticket generation time | 10–15s (manual entry) | <500ms (automated) |
| System uptime | ~95% (ignition SPOF) | >99.5% (AWS managed) |
| False positive rate | N/A | <5% on edge tier |

---

## 2. Architecture Overview

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AUTOMOTIVE INSPECTION TUNNEL                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  VIN Barcode Scanner ──→ [Vehicle Identity Association]           │
│         ↓                                                           │
│  USB 3.0 UVC Camera ──→ Jetson Nano 2GB ────────────────┐         │
│  (mounted on robotic arm                │                │         │
│   or static tunnel)                     │                │         │
│                                         ↓                │         │
│                                   CLIP ViT-B/32         │         │
│                                   TensorRT INT8         │         │
│                                   (~150ms inference)    │         │
│                                         │                │         │
│                         ┌───────────────┴──────┐         │         │
│                         ↓                      ↓         │         │
│                  Confidence ≥ 0.75    Confidence < 0.75 │         │
│                   (PASS/FAIL)          (Anomaly flagged)│         │
│                         │                      │         │         │
│                         │              Anomaly Crop     │         │
│                         │              Extraction       │         │
│                         │              (YOLOv8-nano    │         │
│                         │               or CLIP attn)  │         │
│                         │                      │         │         │
│                         │              500×500 px ROI   │         │
│                         │                      │         │         │
│                         └──────────┬───────────┘         │         │
│                                    ↓                     │         │
│              AWS IoT Core MQTT (X.509 TLS)              │         │
│                   (QoS 1, Device Shadow)                │         │
│                                    │                     │         │
│                ┌───────────────────┼──────────────────┐  │         │
│                ↓                   ↓                  ↓  │         │
│           Lambda Trigger      Lambda Trigger    S3 Write │         │
│         (PASS frames)        (Anomaly frames)  (All imgs) │         │
│                │                   │                  │  │         │
│                │               Step Functions          └──┤         │
│                │                   │                      │         │
│                ↓                   ↓                      │         │
│              S3 → Metrics      SageMaker VLM             │         │
│              (pass/fail ratio)  (PaliGemma 3B)          │         │
│                                 Serverless              │         │
│                                   │                      │         │
│                                   ↓                      │         │
│                        Structured JSON Output:          │         │
│                        {defect_type, severity,          │         │
│                         location, repair_action,        │         │
│                         rework_station}                │         │
│                                   │                      │         │
│                                   ↓                      │         │
│                           Step Functions Router:        │         │
│                           Route by {rework_station}    │         │
│                                   │                      │         │
│                  ┌─────────┬───────┼────────┬───────┐    │         │
│                  ↓         ↓       ↓        ↓       ↓    │         │
│              Paint   Weld   Body   Reject  Manual  │    │         │
│              Touch-up Rework Shop  Queue   Review  │    │         │
│              Bay     Bay    Bay                    │    │         │
│                  │         │       │        │      │    │         │
│                  └─────────┴───────┼────────┴─────┘    │         │
│                                    ↓                      │         │
│                        SAP S/4HANA ERP                   │         │
│                    (Rework ticket creation)             │         │
│                    (Inventory deduction)                │         │
│                    (Rework bay queue update)            │         │
│                                                        │         │
└─────────────────────────────────────────────────────────┘         │
                                                           │         │
                        ┌─────────────────────────────────┘         │
                        │                                            │
                        ↓                                            │
        ┌───────────────────────────────────────────┐               │
        │   SageMaker Model Monitor                 │               │
        │   (Drift detection, retraining alerts)   │               │
        │   (Model registry & versioning)          │               │
        └───────────────────────────────────────────┘               │
                        │                                            │
                        ↓                                            │
        ┌───────────────────────────────────────────┐               │
        │   Data Lake (S3 Parquet)                  │               │
        │   ↓ Athena SQL                            │               │
        │   ↓ Power BI / QuickSight                 │               │
        │   (Defect trends, rework analytics)      │               │
        └───────────────────────────────────────────┘               │
                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Tier Architecture (Confidence-Based Routing)

#### Tier 1: Edge (Jetson Nano)
- **Model:** CLIP ViT-B/32 TensorRT INT8
- **Input:** Full USB camera frame (480–720p)
- **Latency:** ~150ms inference
- **Memory:** ~380MB VRAM
- **Output:** Binary classification (PASS/FAIL) + confidence score [0.0–1.0]
- **Prompts:**
  - Positive: `"a smooth painted car body surface without defects"`
  - Negative: `"a car body with paint defects: scratches, drips, or surface damage"`
- **Decision Rule:**
  - If confidence ≥ 0.75 → **Local PASS/FAIL** (no cloud call)
  - If confidence < 0.75 → **Escalate to Tier 2 (VLM)**

#### Tier 2: Cloud VLM (SageMaker Serverless)
- **Model:** PaliGemma 3B (or Florence-2 alternative)
- **Input:** 500×500 px anomaly crop + structured prompt
- **Latency:** 1.2–2.0s (cold start ~500ms, warm ~200ms)
- **Cost:** Pay-per-invoke, ~$0.001–0.005 per request
- **Scaling:** Auto-scale (typically 10–15% of frames escalate)
- **Output:** Structured JSON
  ```json
  {
    "defect_type": "scratch|paint_drip|weld_defect|dent|blister",
    "severity": "minor|moderate|major",
    "location_description": "front left quarter panel, ~2 inches long",
    "repair_action": "sand and spot repaint",
    "rework_station": "paint_touch_up_bay_02",
    "confidence": 0.92
  }
  ```

---

## 3. Component Breakdown

### 3.1 Edge Components (Jetson Nano)

#### A. USB Camera Capture (`capture.py`)
- **Library:** OpenCV 4.x + libargus (Jetson hardware-accelerated ISP)
- **Resolution:** 1280×720 @ 30 FPS (configurable)
- **Trigger:** Photoelectric sensor on line or GPI input from PLC
- **Buffering:** Ring buffer (10 frames, ~500MB) for offline tolerance
- **Outputs:** Frame → MQTT publish OR local SQS queue if offline

#### B. CLIP Inference (`clip_inference.py`)
- **Model:** `openai/clip-vit-base-patch32` (ViT-B/32)
- **Conversion:** CLIP ONNX → TensorRT INT8 (FP16 fallback)
- **Prompts:** Load from `prompts.json` (automotive-specific)
- **Inference:** ~150ms per frame on Jetson Nano
- **Output:** {class, confidence, embedding}

#### C. Anomaly Crop Extraction (`anomaly_crop.py`)
- **Option A (Lightweight):** YOLOv8-nano pretrained on generic defects
  - Runs ~15–20ms, outputs bounding box
  - Crop to 500×500 px, pad if needed
  - Source: YOLOv8 Ultralytics (Apache 2.0)
- **Option B (Zero-shot):** CLIP attention map visualization
  - Extract attention weights from ViT encoder
  - Generate saliency map, threshold at 90th percentile
  - Crop to 500×500 px ROI
  - More elegant, no extra model download
- **Selected for MVP:** Option B (CLIP attention)

#### D. MQTT Publisher (`mqtt_client.py`)
- **Broker:** AWS IoT Core (MQTT 5.0)
- **Transport:** TLS 1.3 + X.509 client cert
- **Topics:**
  - `vehicles/{vin}/inspection/frame_raw` → full frame (if Pass)
  - `vehicles/{vin}/inspection/anomaly_crop` → 500×500 crop (if escalate)
  - `devices/{device_id}/metrics/health` → heartbeat (5min interval)
- **QoS:** 1 (at-least-once)
- **Offline Buffering:** Local SQLite queue if connection lost
- **Retry:** Exponential backoff (max 5 retries, then DLQ)

#### E. Model Manager (`model_manager.py`)
- **AWS IoT Device Shadow:** Stores current model version + metadata
  - `{clip_model_version, vlm_model_version, prompts_version, timestamp}`
- **OTA Update Trigger:** Shadow delta listener
- **Update Flow:**
  1. S3 download new TensorRT binary
  2. Verify SHA-256 checksum
  3. Atomic rename (no downtime)
  4. Fall back to previous version if inference fails
- **Metrics:** Model load time, inference latency percentiles (p50, p95, p99)

#### F. Config & Prompts (`prompts.json`)
```json
{
  "model": {
    "clip_version": "vit-b-32",
    "tensorrt_precision": "int8",
    "model_s3_path": "s3://my-bucket/models/clip-vit-b32-int8.trt"
  },
  "prompts": {
    "pass": [
      "a smooth painted car body surface without defects",
      "pristine automotive paint with no scratches or drips"
    ],
    "defect": [
      "a deep scratch on painted car body",
      "paint drip or sag on vehicle surface",
      "weld seam gap or incomplete fusion",
      "dent or surface deformation",
      "paint bubble or blister",
      "overspray or contamination on car body"
    ]
  },
  "routing": {
    "confidence_threshold": 0.75,
    "min_crop_size_px": 500,
    "max_anomaly_crops_per_batch": 10
  }
}
```

---

### 3.2 Cloud Components (AWS)

#### A. AWS IoT Core
- **Device Registry:** Jetson Nanos registered as IoT Things
  - **Attributes:** {device_id, serial, mac_address, firmware_version, location}
- **X.509 Certificates:** 1 per Nano, rotated annually
- **Device Shadow:** Tracks model versions, health metrics, target state
- **MQTT Broker:** Receives frame metadata + anomaly crop references
- **Rules Engine:** Forward to Lambda/SQS based on topic pattern
- **Policies:** Least-privilege IAM (publish to own topics only)

#### B. Lambda Functions

**Lambda-1: Edge Frame Processor** (`edge_frame_processor`)
- **Trigger:** IoT Topic: `vehicles/+/inspection/frame_raw`
- **Logic:**
  1. Extract frame from message (or S3 ref)
  2. If `confidence >= 0.75` → increment pass counter
  3. Log to CloudWatch metrics
  4. Archive to S3 Parquet (for analytics)
- **Runtime:** 512MB, 60s timeout
- **Cost:** ~0.0001 per frame

**Lambda-2: Anomaly Escalation Handler** (`anomaly_escalation`)
- **Trigger:** IoT Topic: `vehicles/+/inspection/anomaly_crop`
- **Logic:**
  1. Validate incoming anomaly crop from S3
  2. Enqueue to SQS (VLM queue)
  3. Log anomaly metadata to DynamoDB (audit trail)
- **Runtime:** 256MB, 30s timeout
- **SQS Output:** High-priority queue for VLM processing

**Lambda-3: VLM Orchestrator** (`vlm_orchestrator`)
- **Trigger:** SQS from Anomaly Escalation Handler
- **Logic:**
  1. Invoke SageMaker VLM endpoint (async or sync)
  2. Parse JSON output
  3. Validate schema (defect_type, severity, repair_action, rework_station)
  4. Pass to Step Functions State Machine
- **Runtime:** 512MB, 120s timeout
- **Async Invoke:** SageMaker Async Option (if queue depth > 5)

**Lambda-4: Rework Routing Router** (`rework_router`)
- **Trigger:** Step Functions state change
- **Logic:**
  1. Extract `rework_station` from VLM JSON
  2. Map to SAP plant location + cost center
  3. Call SAP OData API (or mock endpoint)
  4. Route signal to PLC/Ignition via MQTT (if needed)
  5. Publish to DLQ if SAP fails (manual escalation)
- **Runtime:** 512MB, 60s timeout
- **Retry Policy:** 3 retries with exponential backoff

#### C. Step Functions State Machine

```yaml
StartAt: ReceiveAnomalyCrop
States:
  ReceiveAnomalyCrop:
    Type: Task
    Resource: arn:aws:lambda:...:function:anomaly_escalation
    Next: WaitForVLMResult

  WaitForVLMResult:
    Type: Wait
    Seconds: 30
    Next: InvokeVLM

  InvokeVLM:
    Type: Task
    Resource: arn:aws:sagemaker:...:endpoint:paligemma-defect
    Next: ValidateVLMOutput
    Catch:
      - ErrorEquals: ["States.TaskFailed"]
        Next: SendToManualReview

  ValidateVLMOutput:
    Type: Task
    Resource: arn:aws:lambda:...:function:validate_vlm_output
    Next: RouteByDefectType

  RouteByDefectType:
    Type: Choice
    Choices:
      - Variable: "$.defect_type"
        StringEquals: "paint_drip"
        Next: RouteToPaintTouchup
      - Variable: "$.defect_type"
        StringEquals: "weld_defect"
        Next: RouteToWeldRework
      - Variable: "$.severity"
        StringEquals: "major"
        Next: SendToSupervisor
    Default: RouteToPaintTouchup

  RouteToPaintTouchup:
    Type: Task
    Resource: arn:aws:lambda:...:function:rework_router
    Parameters:
      rework_station: "paint_touch_up_bay"
      plant_location: "Building_3_Line_2"
    Next: CreateSAPTicket

  RouteToWeldRework:
    Type: Task
    Resource: arn:aws:lambda:...:function:rework_router
    Parameters:
      rework_station: "weld_rework_bay"
      plant_location: "Building_1_Line_1"
    Next: CreateSAPTicket

  SendToSupervisor:
    Type: Task
    Resource: arn:aws:lambda:...:function:escalate_to_supervisor
    Next: CreateSAPTicket

  CreateSAPTicket:
    Type: Task
    Resource: arn:aws:lambda:...:function:sap_integration
    Next: PublishToMES
    Catch:
      - ErrorEquals: ["States.TaskFailed"]
        Next: SAPFailureDLQ

  PublishToMES:
    Type: Task
    Resource: arn:aws:lambda:...:function:publish_to_mes
    Next: Success

  SAPFailureDLQ:
    Type: Task
    Resource: arn:aws:sqs:...:queue:sap_failure_dlq
    Next: Fail

  SendToManualReview:
    Type: Task
    Resource: arn:aws:sns:...:topic:manual_review_queue
    Next: Fail

  Success:
    Type: Succeed

  Fail:
    Type: Fail
```

#### D. SageMaker Serverless VLM Endpoint

**Endpoint Configuration:**
- **Model:** PaliGemma 3B (HuggingFace transformers)
- **Container:** `huggingface/huggingface-pytorch-tgi:2.0.1`
- **Variant:** Serverless (no static capacity)
- **Auto-scaling:** 2–20 concurrent instances
- **Invocation Method:** Async (S3 input → SQS output) or Sync (REST)
- **Cost:** ~$0.001–0.005 per 1000 tokens

**VLM Prompt Template:**
```
You are an automotive quality inspector analyzing a cropped defect image from a car body assembly line.

Defect Image: [image]

Analyze this image and respond ONLY in valid JSON format with NO markdown, NO preamble, NO explanation:
{
  "defect_type": "scratch|paint_drip|weld_defect|dent|blister|overspray|contamination|unknown",
  "severity": "minor|moderate|major",
  "location_description": "Describe location on vehicle (e.g., 'front left quarter panel, approximately 2 inches from top edge')",
  "repair_action": "Describe the specific repair action (e.g., 'sand down to primer, feather edges, apply base and clear coat')",
  "rework_station": "paint_touch_up_bay|full_repaint_booth|weld_rework_bay|body_shop|manual_review",
  "repair_time_minutes": <integer estimate>,
  "confidence": <float 0.0 to 1.0>
}
```

#### E. SAP S/4HANA Integration (`sap_integration.py`)

**API Method A (OData - recommended for SAP S/4HANA):**
```python
import requests
from datetime import datetime

def create_rework_ticket_sap(defect_data, vin):
    sap_endpoint = "https://sap-erp.company.com/sap/opu/odata/sap/C_REWORKREQUEST_CDS"
    
    payload = {
        "VehicleVIN": vin,
        "RequestType": "REWORK",
        "DefectType": defect_data["defect_type"],
        "Severity": defect_data["severity"],
        "LocationDescription": defect_data["location_description"],
        "RepairAction": defect_data["repair_action"],
        "PlantID": defect_data["plant_location"],
        "ReworkStation": defect_data["rework_station"],
        "CreationTime": datetime.utcnow().isoformat(),
        "ImageURL": defect_data["image_s3_url"],
        "MLConfidence": defect_data["vlm_confidence"]
    }
    
    response = requests.post(
        sap_endpoint,
        json=payload,
        headers={"Authorization": f"Bearer {sap_token}"},
        timeout=30
    )
    
    if response.status_code in [200, 201]:
        return {"sap_ticket_id": response.json()["ReworkRequestID"]}
    else:
        raise Exception(f"SAP API error: {response.status_code}")
```

**API Method B (Mock SAP Endpoint - for portfolio PoC):**
```python
# FastAPI mock SAP endpoint (runs locally or on Lambda)
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ReworkTicket(BaseModel):
    vin: str
    defect_type: str
    severity: str
    repair_action: str
    rework_station: str

@app.post("/sap/rework-request")
async def create_ticket(ticket: ReworkTicket):
    # Mock: just echo back with a ticket ID
    return {
        "sap_ticket_id": f"SAP-{datetime.now().timestamp()}",
        "status": "CREATED",
        "plant_route": ticket.rework_station
    }
```

#### F. MES FastAPI Microservice (`mes_service.py`)

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import json

app = FastAPI(title="Automotive MES Integration")

class DefectRecord(BaseModel):
    vin: str
    inspection_time: str
    defect_type: str
    severity: str
    location_description: str
    repair_action: str
    rework_station: str
    image_s3_url: str
    clip_confidence: float
    vlm_confidence: float
    vlm_model_version: str

class InspectionResult(BaseModel):
    vin: str
    result: str  # "PASS" or "REWORK"
    inspection_time: str
    image_s3_url: str
    clip_confidence: float

# Database: DynamoDB table "defect_log"
@app.post("/defect/log")
async def log_defect(record: DefectRecord):
    """Log a rework-triggered defect to MES."""
    try:
        # Write to DynamoDB
        dynamodb.Table("defect_log").put_item(Item=record.dict())
        
        # Publish to SNS for MES subscribers
        sns.publish(
            TopicArn="arn:aws:sns:...:defect_log",
            Message=json.dumps(record.dict())
        )
        
        return {"status": "logged", "vin": record.vin}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/inspection/pass")
async def log_pass(record: InspectionResult):
    """Log a PASS inspection result."""
    dynamodb.Table("inspection_metrics").put_item(Item=record.dict())
    return {"status": "logged", "result": "PASS"}

@app.get("/defect/{vin}")
async def get_defect_history(vin: str):
    """Retrieve defect history for a vehicle VIN."""
    response = dynamodb.Table("defect_log").query(
        KeyConditionExpression="vin = :vin",
        ExpressionAttributeValues={":vin": vin}
    )
    return response["Items"]
```

---

### 3.3 Data & Storage

#### A. S3 Bucket Structure
```
s3://automotive-quality-data/
├── models/
│   ├── clip-vit-b32-int8.trt
│   ├── clip-vit-b32-int8.bin
│   └── onnx/
│       └── clip-vit-b32.onnx
├── images/
│   ├── raw/
│   │   └── {year}/{month}/{day}/vehicle-{vin}-{timestamp}.jpg
│   ├── anomalies/
│   │   └── {year}/{month}/{day}/anomaly-{vin}-{timestamp}-crop.jpg
│   └── archive/ (lifecycle: 30-day expiry)
├── parquet/ (data lake)
│   ├── defect_logs/
│   │   └── year=2025/month=01/day=15/defect_logs.parquet
│   └── inspection_metrics/
│       └── year=2025/month=01/day=15/metrics.parquet
└── configs/
    └── prompts.json
```

#### B. DynamoDB Tables

**Table 1: `defect_log`**
- **Partition Key:** `vin` (vehicle VIN)
- **Sort Key:** `inspection_timestamp` (ISO 8601)
- **Attributes:**
  - `defect_type`, `severity`, `repair_action`, `rework_station`
  - `clip_confidence`, `vlm_confidence`
  - `image_s3_url`, `sap_ticket_id`
  - `repair_completion_time` (added post-rework)
- **TTL:** 2 years (archive to Glacier after 90 days)

**Table 2: `inspection_metrics`**
- **Partition Key:** `device_id` (Jetson Nano serial)
- **Sort Key:** `inspection_timestamp`
- **Attributes:**
  - `result` (PASS/REWORK), `confidence`
  - `model_version`, `inference_latency_ms`
  - `frame_resolution`, `lighting_conditions` (optional)
- **TTL:** 6 months
- **GSI:** `inspection_date-index` (for daily reports)

**Table 3: `model_registry`**
- **Partition Key:** `model_id` (e.g., `clip-vit-b32-int8`)
- **Attributes:**
  - `version`, `s3_path`, `sha256_checksum`
  - `training_date`, `validation_accuracy`
  - `deployment_status` (ACTIVE, DEPRECATED, TESTING)
  - `rollback_version`

---

### 3.4 Monitoring & MLOps

#### A. CloudWatch Metrics (Custom)
```
automotive/quality/
├── edge/
│   ├── ClipInferenceLatenmy (ms)
│   ├── ConfidenceScore (0–100 histogram)
│   ├── AnomalyDetectionRate (%)
│   └── OfflineBufferSize (frames)
├── cloud/
│   ├── VLMInvocationLatency (s)
│   ├── SAPIntegrationLatency (s)
│   ├── ReworkRoutingAccuracy (%)
│   └── EndToEndLatency (s)
└── business/
    ├── DefectEscapeRate (%)
    ├── ReworkCycleTime (minutes)
    └── CostPerInspection ($)
```

#### B. SageMaker Model Monitor
- **Baseline Dataset:** 1000 labeled inspection frames (PASS/REWORK)
- **Monitoring Schedule:** Daily 6 AM UTC
- **Drift Detection:**
  - Data drift (input distribution shift)
  - Model performance drift (accuracy vs. baseline)
  - Model bias (false positive rate by defect type)
- **Alert Threshold:** >5% accuracy drop → SNS notification
- **Auto-Trigger Retraining:** If drift detected for 3 consecutive days

#### C. Model Versioning & Rollback
- **Model Registry:**
  - CLIP: Pinned to specific HuggingFace checkpoint + TensorRT build
  - VLM: SageMaker Model Registry with auto-versioning
- **Deployment Strategy:**
  - Canary: Route 5% of anomalies to new VLM for 24h
  - Shadow: Run old + new models in parallel, compare outputs
  - Rollback: Device Shadow update triggers atomic revert on Jetson
- **Testing:** Unit tests + integration tests on sample anomaly crops

---

## 4. Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| Edge OS | Jetpack 4.6 (Ubuntu 18.04) | Official Jetson support |
| Edge ML Framework | PyTorch 1.10 + TensorRT 8.2 | Nvidia-optimized, low VRAM |
| CLIP Model | openai/clip-vit-base-patch32 | Zero-shot, fast, well-documented |
| Anomaly Crop | CLIP attention map | No extra model, explainable |
| VLM | PaliGemma 3B | Open-source, serverless-friendly |
| Cloud Orchestration | AWS Step Functions | Visual, serverless, audit trails |
| Inference Scaling | SageMaker Serverless | Pay-per-invoke, auto-scale |
| Message Broker | AWS IoT Core MQTT 5.0 | X.509 secure, Device Shadow |
| Serverless Compute | AWS Lambda | Sub-100ms cold start (esp. for routing) |
| Database | DynamoDB | Serverless, auto-scale, ACID |
| Data Lake | S3 + Athena | Parquet format, SQL queries |
| Monitoring | CloudWatch + SageMaker Model Monitor | Native AWS integration |
| IaC | AWS CloudFormation / Terraform | Infrastructure as code |
| VCS | GitHub + GitHub Actions | CI/CD for lambda/model updates |

---

## 5. Implementation Timeline (9 Weeks)

### Week 1–2: Edge Foundation & CLIP Setup
**Deliverables:**
- Jetson Nano environment: Jetpack, CUDA, cuDNN, TensorRT
- CLIP model download + ONNX conversion
- TensorRT INT8 quantization + calibration dataset (100 synthetic/public images)
- `capture.py`: USB camera streaming @ 30 FPS, ring buffer
- `clip_inference.py`: Inference loop (~150ms per frame)
- Unit tests: inference latency, memory footprint
- **Success Criteria:** <200ms end-to-end inference (capture → CLIP → confidence)

### Week 3–4: Anomaly Crop & Edge MQTT
**Deliverables:**
- `anomaly_crop.py`: CLIP attention map extraction → 500×500 px ROI
- `mqtt_client.py`: AWS IoT Core X.509 provisioning, topic publish
- `model_manager.py`: Device Shadow listener + OTA update simulation
- Offline buffering: SQLite queue on Jetson (test disconnection)
- Integration test: Full edge pipeline (USB cam → CLIP → crop → MQTT)
- **Success Criteria:** <500ms total latency, 100% message delivery (with retry)

### Week 5: Cloud Infrastructure & Lambda Setup
**Deliverables:**
- AWS IoT Core: Device registry, certificates, rules engine
- S3 bucket: Create folder structure, lifecycle policies
- DynamoDB: Create tables (defect_log, inspection_metrics, model_registry)
- Lambda-1 (Edge Frame Processor): Parse IoT messages, log metrics
- Lambda-2 (Anomaly Escalation): Validate crop, enqueue to SQS
- Lambda-3 (VLM Orchestrator): Stub for SageMaker endpoint
- IAM policies: Least-privilege roles
- CloudFormation template: Infrastructure as code
- **Success Criteria:** End-to-end message flow: Jetson → IoT → Lambda → S3 (5s latency)

### Week 6–7: VLM Integration & Rework Routing
**Deliverables:**
- SageMaker Serverless endpoint: Deploy PaliGemma 3B
- VLM prompt engineering: Test with 50–100 real/synthetic defect crops
- Lambda-3 update: Full VLM invocation + output validation
- Lambda-4 (Rework Router): Route logic by defect_type
- Step Functions state machine: Anomaly → VLM → Routing → SAP
- SAP Integration: Mock endpoint (FastAPI) + OData API skeleton
- MES FastAPI service: Log defect records to DynamoDB
- **Success Criteria:** VLM end-to-end latency <2s, JSON schema validation 100%, rework routing accuracy >95%

### Week 8: Testing, Monitoring & Optimization
**Deliverables:**
- SageMaker Model Monitor: Baseline setup, drift detection rules
- CloudWatch dashboards: Real-time latency, defect rate, cost
- Integration tests: 100 synthetic inspection cycles (Jetson → SAP)
- Load testing: Jetson Nano concurrent anomaly crops (stress test)
- Edge-to-cloud latency profiling: Identify bottlenecks
- Cost estimation: per-inspection breakdown (VLM, Lambda, storage)
- **Success Criteria:** <3s E2E latency P95, <$0.02 cost per inspection

### Week 9: Documentation, Portfolio & Deployment Prep
**Deliverables:**
- Architecture diagrams (Visio/Lucidchart)
- Code repository: GitHub with README, setup guide, deployment playbook
- Portfolio documentation:
  - Problem statement & solution narrative
  - Architecture decision record (ADR) for each major choice
  - Performance benchmarks (latency, accuracy, cost)
  - Deployment instructions (for hiring teams)
- Video walkthrough: Jetson inspection, defect detection, rework ticket generation
- SAP integration runbook: How to connect to real ERP
- **Success Criteria:** Hiring manager can deploy system in <4 hours from GitHub

---

## 6. Code Modules & Repository Structure

```
automotive-quality-inspection/
├── edge/
│   ├── capture.py                 # USB camera streaming
│   ├── clip_inference.py          # CLIP TensorRT inference
│   ├── anomaly_crop.py            # Attention map extraction
│   ├── mqtt_client.py             # IoT Core MQTT publisher
│   ├── model_manager.py           # Device Shadow OTA updates
│   ├── offline_buffer.py          # SQLite queue for offline tolerance
│   ├── main.py                    # Orchestration loop
│   ├── config.yaml                # Edge config (topics, model paths)
│   ├── prompts.json               # Zero-shot prompts
│   ├── requirements.txt           # Dependencies
│   ├── tests/
│   │   ├── test_inference.py
│   │   ├── test_mqtt.py
│   │   └── test_offline_buffer.py
│   └── docker/
│       └── Dockerfile            # Optional: container for dev
│
├── cloud/
│   ├── lambda/
│   │   ├── edge_frame_processor/
│   │   │   └── index.py
│   │   ├── anomaly_escalation/
│   │   │   └── index.py
│   │   ├── vlm_orchestrator/
│   │   │   └── index.py
│   │   ├── rework_router/
│   │   │   └── index.py
│   │   └── sap_integration/
│   │       └── index.py
│   ├── step_functions/
│   │   └── rework_routing_statemachine.json
│   ├── sagemaker/
│   │   ├── endpoint_config.json
│   │   └── vlm_prompt_template.txt
│   ├── mes_service/
│   │   ├── main.py               # FastAPI app
│   │   ├── models.py             # Pydantic schemas
│   │   ├── requirements.txt
│   │   └── tests/
│   │       └── test_endpoints.py
│   ├── iot_core/
│   │   ├── device_policy.json
│   │   └── iot_rules.json
│   └── terraform/
│       ├── main.tf               # VPC, Lambda, DynamoDB
│       ├── iam.tf                # Roles & policies
│       ├── s3.tf                 # Bucket + lifecycle
│       ├── sagemaker.tf          # VLM endpoint
│       └── variables.tf
│
├── mlops/
│   ├── sagemaker_monitor.py      # Drift detection config
│   ├── model_registry.py         # Version tracking
│   ├── calibration_dataset/      # INT8 quantization data
│   │   └── automotive_defects_100.txt
│   └── evaluation/
│       ├── eval_metrics.py       # Accuracy, confusion matrix
│       └── benchmark_latency.py  # Edge inference perf
│
├── tests/
│   ├── integration_test.py        # End-to-end Jetson → SAP
│   ├── load_test.py              # Concurrent anomaly processing
│   └── fixtures/
│       ├── sample_defect_crop.jpg
│       ├── vlm_response_mock.json
│       └── sap_api_response_mock.json
│
├── docs/
│   ├── ARCHITECTURE.md           # Detailed tech spec
│   ├── DEPLOYMENT.md             # Step-by-step setup
│   ├── OPERATIONS.md             # Monitoring, troubleshooting
│   ├── SAP_INTEGRATION.md        # OData API walkthrough
│   ├── COST_MODEL.md             # Per-inspection breakdown
│   └── diagrams/
│       ├── architecture.drawio
│       └── data_flow.drawio
│
├── examples/
│   ├── sample_inspection_log.json
│   ├── sample_vlm_output.json
│   └── sample_sap_ticket.json
│
├── .github/
│   └── workflows/
│       ├── edge_tests.yml        # Test Jetson code
│       ├── lambda_deploy.yml     # Deploy Lambda on push
│       └── terraform_plan.yml    # Terraform validate
│
├── README.md                      # Project overview
├── LICENSE                        # Apache 2.0
└── .gitignore
```

---

## 7. Success Metrics & Validation

### Tier 1: Technical KPIs
| KPI | Baseline | Target | Week |
|---|---|---|---|
| Edge inference latency (p95) | N/A | <200ms | 2 |
| E2E latency PASS path (p95) | N/A | <500ms | 4 |
| E2E latency REWORK path (p95) | N/A | <2s | 7 |
| VLM confidence accuracy | N/A | >90% | 7 |
| Anomaly crop extraction accuracy | N/A | >95% | 4 |
| System uptime | N/A | >99% | 8 |
| Cost per inspection | N/A | <$0.02 | 8 |

### Tier 2: Business KPIs (Simulated)
- **Defect escape rate:** 2–3% (manual) → <0.5% (automated)
- **Inspection cycle time:** 45–60s → <3s
- **Rework ticket generation:** 10–15s → <500ms
- **Operator training time:** ~2 weeks → 2 hours (just setup)

### Tier 3: Portfolio KPIs
- **Code quality:** >80% test coverage (unit + integration)
- **Documentation:** Hireable in <4 hours from README
- **Reproducibility:** One-command deployment (terraform apply)
- **Security:** X.509 TLS, IAM policies, no hardcoded secrets

---

## 8. Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Jetson Nano VRAM exhaustion | Medium | High | Profile early (Week 2), consider INT8 quantization, fallback to ViT-Small |
| CLIP zero-shot accuracy insufficient | Medium | Medium | Curate automotive-specific prompts (Week 1), test on 50–100 real defects |
| VLM latency > 2s (cold start) | Low | Medium | Warm up endpoint with dummy invokes, use async if needed, cache prompts |
| SAP OData API unavailable | Low | High | Mock SAP endpoint ready (Week 6), test integration with stub |
| MQTT broker downtime | Low | Medium | Local offline buffer on Jetson (Week 4), exponential backoff retry |
| Data drift (model degradation) | Medium | High | SageMaker Model Monitor active (Week 8), alert at >5% accuracy drop |
| Cost overrun (VLM invokes) | Low | Medium | Strict confidence routing (only ~10–15% escalate), track invocations in CloudWatch |

---

## 9. Portfolio Positioning & Narrative

### Elevator Pitch (30 seconds)
> *"Built an end-to-end automotive defect detection system combining edge AI and cloud VLM. Jetson Nano runs CLIP inference for high-speed anomaly detection; ambiguous cases escalate to PaliGemma VLM for structured analysis. Output automatically generates SAP rework tickets and routes vehicles to the correct rework station — reducing inspection cycle time from 45s to <3s."*

### One-Pager Talking Points
1. **Edge AI (Jetson Nano + CLIP)**
   - TensorRT INT8 quantization: 150ms inference @ 380MB VRAM
   - Zero-shot learning: New defect types = prompt update only
   - Confidence-based routing: Escalate <10% to cloud

2. **Cloud VLM (SageMaker Serverless + PaliGemma)**
   - Structured JSON output: {defect_type, severity, repair_action, rework_station}
   - Cost-efficient: Pay-per-invoke, auto-scales
   - Audit trail: All NL descriptions stored for ML ops

3. **ERP Integration (AWS + SAP)**
   - Orchestrated via Step Functions state machine
   - Lambda + SQS for resilience
   - OData API skeleton ready for real SAP deployment

4. **MLOps Rigor**
   - SageMaker Model Monitor: Drift detection in hours (vs. weeks in legacy)
   - Model versioning + rollback via IoT Device Shadow
   - >80% test coverage

5. **Real-World Applicability**
   - Tested on Jetson Nano hardware (actual constraints)
   - Designed for automotive post-paint/post-weld inspection
   - Scalable to multiple inspection stations

---

## 10. Appendix: Deployment Playbook (TL;DR)

### Prerequisites
- NVIDIA Jetson Nano 2GB + Jetpack 4.6
- USB 3.0 UVC camera
- AWS account with IoT Core, SageMaker, Lambda enabled
- GitHub repo cloned locally

### Quick Start (Week 1–2)
```bash
# On Jetson Nano
git clone https://github.com/vgandhi1/automotive-quality-inspection.git
cd automotive-quality-inspection/edge
./setup.sh                # Install deps, download CLIP, quantize
python main.py --config config.yaml --test-offline-only
# (No camera needed yet; test with synthetic frames)
```

### Full Deployment (Week 5–7)
```bash
# AWS infrastructure
cd ../cloud/terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
# ^ Creates IoT Core, Lambda, DynamoDB, S3, SageMaker endpoint

# Deploy Lambda functions
cd ../lambda
./deploy_all.sh

# Deploy Step Functions state machine
aws stepfunctions create-state-machine \
  --name ReworkRoutingStateMachine \
  --definition file://step_functions/rework_routing_statemachine.json

# Provision Jetson IoT certificate & deploy edge code
cd ../../edge
./provision_iot_cert.sh
python main.py --config config.yaml --mqtt-broker <YOUR_IOT_ENDPOINT>
```

### Validation
```bash
# Integration test (100 synthetic anomalies)
pytest tests/integration_test.py -v --log-cli-level=INFO

# Latency profiling
python mlops/benchmark_latency.py --num_samples=100 --output=latency_report.json

# Cost estimation
cat docs/COST_MODEL.md  # Expected <$0.02 per inspection
```

---

## 11. Conclusion

This **Visual Quality Inspection & Rework Routing Engine** demonstrates full-stack systems engineering:
- **Edge:** Optimized low-latency inference (CLIP TensorRT) on constrained hardware
- **Cloud:** Serverless, scalable architecture for ambiguous cases (VLM + Step Functions)
- **ERP:** Structured integration with manufacturing systems (SAP mock + OData skeleton)
- **MLOps:** Production-grade monitoring, versioning, and drift detection
- **Portfolio:** Hireable narrative (problem → architecture → implementation → deployment)

The architecture is **generalizable** to other manufacturing domains (semiconductor, electronics, textiles) while **specific enough** to demonstrate automotive expertise. Total 9-week build; deployment playbook included for rapid handoff.

---

**Document Version:** 1.0  
**Last Updated:** April 18, 2026  
**Author:** Claude (Anthropic)  
**Status:** Ready for Implementation
