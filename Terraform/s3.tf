data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "main_bucket" {
  # S3 bucket names are globally unique across all AWS accounts, so suffix
  # with the account ID to guarantee uniqueness.
  bucket = "${local.application_name}-bucket-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_object" "data_file" {
  bucket = aws_s3_bucket.main_bucket.bucket
  key    = "${var.s3_data_key}/data.jsonl"
  source = "${path.root}/../Data/data.jsonl"
}

resource "aws_s3_object" "lambda_layer_s3" {
  bucket = aws_s3_bucket.main_bucket.bucket
  key    = "lambda-layers/${local.application_name}-python-dependency-layer.zip"
  source = data.archive_file.lambda_layer_zip.output_path
  etag   = data.archive_file.lambda_layer_zip.output_md5

  depends_on = [data.archive_file.lambda_layer_zip]
}
