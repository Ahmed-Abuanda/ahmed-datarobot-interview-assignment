terraform {
  required_providers {
    opensearch = {
      source  = "opensearch-project/opensearch"
      version = "~> 2.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "5.81.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "3.2.3"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "opensearch" {
  url               = "https://${aws_opensearch_domain.rag_db.endpoint}"
  aws_region        = var.aws_region
  healthcheck       = false
  # Skip the version-detection ping (5s timeout) — match what opensearch.tf sets.
  opensearch_version = "2.11.0"
}
