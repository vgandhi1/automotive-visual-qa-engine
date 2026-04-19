variable "aws_region" {
  type        = string
  description = "AWS region for all resources"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  default     = "automotive-quality"
}

variable "sap_api_url" {
  type        = string
  description = "HTTPS endpoint for SAP mock or OData service (fixed env/config, not user input)"
  default     = ""
}
