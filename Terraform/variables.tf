variable "aws_region" {
  description = "Region AWS Resources will be created"
  default     = "eu-central-1"
}

variable "python_version" {
  description = "Version of python used by lambda functions"
  default     = "3.12"
}

variable "s3_data_key" {
  description = "Location of data files in s3 bucket"
  default     = "data/"
}

variable "anthropic_api_key" {
  description = "Anthropic API key for the agent's Claude model. Pass via TF_VAR_anthropic_api_key env var or -var on the CLI; do NOT commit a value."
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key for product and query embeddings. Pass via TF_VAR_openai_api_key env var or -var on the CLI; do NOT commit a value."
  type        = string
  sensitive   = true
}