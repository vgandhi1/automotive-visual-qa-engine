output "inspection_bucket" {
  value = aws_s3_bucket.inspection.bucket
}

output "vlm_queue_url" {
  value = aws_sqs_queue.vlm.url
}

output "rework_state_machine_arn" {
  value = aws_sfn_state_machine.rework.arn
}

output "lambda_edge_frame_processor" {
  value = aws_lambda_function.edge_frame_processor.arn
}

output "lambda_vlm_orchestrator" {
  value = aws_lambda_function.vlm_orchestrator.arn
}
