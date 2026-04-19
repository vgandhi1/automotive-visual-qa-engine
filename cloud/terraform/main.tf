terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  name = var.project_name
}

resource "random_id" "suffix" {
  byte_length = 2
}

resource "aws_s3_bucket" "inspection" {
  bucket = "${local.name}-data-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_versioning" "inspection" {
  bucket = aws_s3_bucket.inspection.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_sqs_queue" "vlm" {
  name = "${local.name}-vlm"
}

resource "aws_dynamodb_table" "defect_log" {
  name         = "${local.name}_defect_log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "vin"
  range_key    = "inspection_timestamp"

  attribute {
    name = "vin"
    type = "S"
  }
  attribute {
    name = "inspection_timestamp"
    type = "S"
  }
}

resource "aws_dynamodb_table" "inspection_metrics" {
  name         = "${local.name}_inspection_metrics"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "inspection_timestamp"

  attribute {
    name = "device_id"
    type = "S"
  }
  attribute {
    name = "inspection_timestamp"
    type = "S"
  }
}

resource "aws_dynamodb_table" "model_registry" {
  name         = "${local.name}_model_registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "model_id"

  attribute {
    name = "model_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "anomaly_audit" {
  name         = "${local.name}_anomaly_audit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "vin"
  range_key    = "inspection_timestamp"

  attribute {
    name = "vin"
    type = "S"
  }
  attribute {
    name = "inspection_timestamp"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

data "archive_file" "edge_frame_processor" {
  type        = "zip"
  output_path = "${path.module}/build/edge_frame_processor.zip"
  source {
    content  = file("${path.module}/../lambda/edge_frame_processor/index.py")
    filename = "index.py"
  }
}

data "archive_file" "anomaly_escalation" {
  type        = "zip"
  output_path = "${path.module}/build/anomaly_escalation.zip"
  source {
    content  = file("${path.module}/../lambda/anomaly_escalation/index.py")
    filename = "index.py"
  }
}

data "archive_file" "vlm_orchestrator" {
  type        = "zip"
  output_path = "${path.module}/build/vlm_orchestrator.zip"
  source {
    content  = file("${path.module}/../lambda/vlm_orchestrator/index.py")
    filename = "index.py"
  }
}

data "archive_file" "rework_router" {
  type        = "zip"
  output_path = "${path.module}/build/rework_router.zip"
  source {
    content  = file("${path.module}/../lambda/rework_router/index.py")
    filename = "index.py"
  }
}

data "archive_file" "sap_integration" {
  type        = "zip"
  output_path = "${path.module}/build/sap_integration.zip"
  source {
    content  = file("${path.module}/../lambda/sap_integration/index.py")
    filename = "index.py"
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_inline" {
  statement {
    sid = "S3Write"
    actions = [
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.inspection.arn}/*"]
  }
  statement {
    sid = "DynamoWrite"
    actions = [
      "dynamodb:PutItem",
    ]
    resources = [
      aws_dynamodb_table.defect_log.arn,
      aws_dynamodb_table.inspection_metrics.arn,
      aws_dynamodb_table.model_registry.arn,
      aws_dynamodb_table.anomaly_audit.arn,
    ]
  }
  statement {
    sid = "SQSWrite"
    actions = [
      "sqs:SendMessage",
    ]
    resources = [aws_sqs_queue.vlm.arn]
  }
  statement {
    sid = "SQSConsume"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.vlm.arn]
  }
  statement {
    sid = "SageMakerInvoke"
    actions = [
      "sagemaker:InvokeEndpoint",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_inline" {
  name   = "${local.name}-lambda-inline"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_inline.json
}

resource "aws_iam_role_policy" "vlm_start_sfn" {
  name = "${local.name}-vlm-start-sfn"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["states:StartExecution"]
      Resource = aws_sfn_state_machine.rework.arn
    }]
  })
}

resource "aws_lambda_function" "edge_frame_processor" {
  function_name    = "${local.name}-edge-frame-processor"
  role             = aws_iam_role.lambda.arn
  handler          = "index.handler"
  filename         = data.archive_file.edge_frame_processor.output_path
  source_code_hash = data.archive_file.edge_frame_processor.output_base64sha256
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 512
  environment {
    variables = {
      INSPECTION_BUCKET = aws_s3_bucket.inspection.bucket
    }
  }
}

resource "aws_lambda_function" "anomaly_escalation" {
  function_name    = "${local.name}-anomaly-escalation"
  role             = aws_iam_role.lambda.arn
  handler          = "index.handler"
  filename         = data.archive_file.anomaly_escalation.output_path
  source_code_hash = data.archive_file.anomaly_escalation.output_base64sha256
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256
  environment {
    variables = {
      VLM_QUEUE_URL        = aws_sqs_queue.vlm.url
      ANOMALY_AUDIT_TABLE  = aws_dynamodb_table.anomaly_audit.name
    }
  }
}

resource "aws_lambda_function" "rework_router" {
  function_name    = "${local.name}-rework-router"
  role             = aws_iam_role.lambda.arn
  handler          = "index.handler"
  filename         = data.archive_file.rework_router.output_path
  source_code_hash = data.archive_file.rework_router.output_base64sha256
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 512
}

resource "aws_lambda_function" "sap_integration" {
  function_name    = "${local.name}-sap-integration"
  role             = aws_iam_role.lambda.arn
  handler          = "index.handler"
  filename         = data.archive_file.sap_integration.output_path
  source_code_hash = data.archive_file.sap_integration.output_base64sha256
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 512
  environment {
    variables = {
      SAP_API_URL = var.sap_api_url
    }
  }
}

resource "aws_sfn_state_machine" "rework" {
  name     = "${local.name}-rework-routing"
  role_arn = aws_iam_role.sfn.arn
  definition = templatefile("${path.module}/../step_functions/rework_routing_statemachine.json.tpl", {
    rework_router_arn   = aws_lambda_function.rework_router.arn
    sap_integration_arn = aws_lambda_function.sap_integration.arn
  })
}

resource "aws_lambda_function" "vlm_orchestrator" {
  function_name    = "${local.name}-vlm-orchestrator"
  role             = aws_iam_role.lambda.arn
  handler          = "index.handler"
  filename         = data.archive_file.vlm_orchestrator.output_path
  source_code_hash = data.archive_file.vlm_orchestrator.output_base64sha256
  runtime          = "python3.12"
  timeout          = 120
  memory_size      = 512
  environment {
    variables = {
      REWORK_STATE_MACHINE_ARN = aws_sfn_state_machine.rework.arn
      VLM_ENDPOINT_NAME        = ""
    }
  }
  depends_on = [
    aws_sfn_state_machine.rework,
    aws_iam_role_policy.vlm_start_sfn,
  ]
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.name}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn_invoke" {
  statement {
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [
      aws_lambda_function.rework_router.arn,
      aws_lambda_function.sap_integration.arn,
    ]
  }
}

resource "aws_iam_role_policy" "sfn_invoke" {
  name   = "${local.name}-sfn-invoke"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn_invoke.json
}

resource "aws_lambda_permission" "sfn_rework" {
  statement_id  = "AllowSfnInvokeReworkRouter"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rework_router.function_name
  principal     = "states.amazonaws.com"
  source_arn    = aws_sfn_state_machine.rework.arn
}

resource "aws_lambda_permission" "sfn_sap" {
  statement_id  = "AllowSfnInvokeSap"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sap_integration.function_name
  principal     = "states.amazonaws.com"
  source_arn    = aws_sfn_state_machine.rework.arn
}

resource "aws_lambda_event_source_mapping" "vlm_queue" {
  event_source_arn = aws_sqs_queue.vlm.arn
  function_name    = aws_lambda_function.vlm_orchestrator.arn
  batch_size       = 1
  enabled          = true
}
