locals {
  lambda_layer_root = "lambda_libraries"
}

resource "null_resource" "install_lambda_libraries" {
  triggers = {
    requirements_hash = filemd5("${path.root}/../Resources/requirements.txt")
    python_version    = var.python_version
  }

  provisioner "local-exec" {
    command = "rm -rf ${path.root}/../Resources/${local.lambda_layer_root}/python_dependency_layer && pip3 install -r ${path.root}/../Resources/requirements.txt -t ${path.root}/../Resources/${local.lambda_layer_root}/python_dependency_layer/python/lib/python${var.python_version}/site-packages --only-binary=:all: --python-version ${var.python_version} --platform manylinux2014_x86_64"
  }
}

data "archive_file" "lambda_layer_zip" {
  depends_on = [null_resource.install_lambda_libraries]
  excludes   = ["venv"]

  type        = "zip"
  source_dir  = "${path.root}/../Resources/${local.lambda_layer_root}/python_dependency_layer"
  output_path = "${path.root}/../Resources/${local.lambda_layer_root}/python_dependency_layer.zip"
}

resource "aws_lambda_layer_version" "universal_lambda_layer" {
  layer_name               = "${local.application_name}-lambda-layer"
  s3_bucket                = aws_s3_bucket.main_bucket.bucket
  s3_key                   = aws_s3_object.lambda_layer_s3.key
  compatible_runtimes      = ["python${var.python_version}"]
  compatible_architectures = ["x86_64"]

  depends_on = [aws_s3_object.lambda_layer_s3]
}

data "archive_file" "text_embedder_lambda_files" {
  type        = "zip"
  source_dir  = "${path.root}/../Resources/text_embedder_lambda/"
  excludes    = ["requirements.txt"]
  output_path = "${path.root}/text_embedder_lambda.zip"
}

resource "aws_lambda_function" "text_embedder_lambda_function" {
  function_name = "${local.application_name}-text-embedder"

  role = aws_iam_role.general_lambda_role.arn

  filename         = data.archive_file.text_embedder_lambda_files.output_path
  source_code_hash = data.archive_file.text_embedder_lambda_files.output_base64sha256

  runtime     = "python${var.python_version}"
  handler     = "lambda_function.lambda_handler"
  timeout     = 900
  memory_size = 512

  layers = [aws_lambda_layer_version.universal_lambda_layer.arn]

  environment {
    variables = {
      S3_BUCKET         = aws_s3_bucket.main_bucket.bucket
      OPENAI_API_KEY    = var.openai_api_key
      EMBEDDING_MODEL   = "text-embedding-3-small"
      EMBED_DIMENSIONS  = "1024"
      OPENSEARCH_DOMAIN = aws_opensearch_domain.rag_db.endpoint
      INDEX_NAME        = opensearch_index.products_main.name
      MAX_RECORDS       = "200"  # OpenAI is cheap; bump for richer catalog
      EMBED_DELAY       = "0.0"  # OpenAI has high RPM, no delay needed
    }
  }

  depends_on = [
    data.archive_file.text_embedder_lambda_files,
    aws_lambda_layer_version.universal_lambda_layer
  ]
}

data "archive_file" "invoke_agent_lambda_files" {
  type        = "zip"
  source_dir  = "${path.root}/../Resources/invoke_agent_lambda/"
  excludes    = ["requirements.txt"]
  output_path = "${path.root}/invoke_agent_lambda.zip"
}

resource "aws_lambda_function" "invoke_agent_lambda_function" {
  function_name = "${local.application_name}-invoke-agent"

  role = aws_iam_role.general_lambda_role.arn

  filename         = data.archive_file.invoke_agent_lambda_files.output_path
  source_code_hash = data.archive_file.invoke_agent_lambda_files.output_base64sha256

  runtime     = "python${var.python_version}"
  handler     = "lambda_function.lambda_handler"
  timeout     = 120
  memory_size = 512

  layers = [aws_lambda_layer_version.universal_lambda_layer.arn]

  environment {
    variables = {
      MCP_URL           = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/mcp"
      AGENT_MODEL       = "claude-haiku-4-5"
      ANTHROPIC_API_KEY = var.anthropic_api_key
      PG_HOST           = split(":", aws_db_instance.postgres.endpoint)[0]
      PG_DB             = aws_db_instance.postgres.db_name
      PG_USER           = aws_db_instance.postgres.username
      PG_PASSWORD       = "admin123"
    }
  }

  depends_on = [
    data.archive_file.invoke_agent_lambda_files,
    aws_lambda_layer_version.universal_lambda_layer
  ]
}

data "archive_file" "tools_mcp_lambda_files" {
  type        = "zip"
  source_dir  = "${path.root}/../Resources/tools_mcp_lambda/"
  excludes    = ["requirements.txt"]
  output_path = "${path.root}/tools_mcp_lambda.zip"
}

resource "aws_lambda_function" "tools_mcp_lambda_function" {
  function_name = "${local.application_name}-tools-mcp"
  role          = aws_iam_role.general_lambda_role.arn

  filename         = data.archive_file.tools_mcp_lambda_files.output_path
  source_code_hash = data.archive_file.tools_mcp_lambda_files.output_base64sha256

  runtime     = "python${var.python_version}"
  handler     = "lambda_function.handler"
  timeout     = 30
  memory_size = 512

  layers = [aws_lambda_layer_version.universal_lambda_layer.arn]

  environment {
    variables = {
      OPENSEARCH_DOMAIN = aws_opensearch_domain.rag_db.endpoint
      MAIN_INDEX_NAME   = opensearch_index.products_main.name
      OPENAI_API_KEY    = var.openai_api_key
      EMBEDDING_MODEL   = "text-embedding-3-small"
      EMBED_DIMENSIONS  = "1024"
      PG_HOST           = split(":", aws_db_instance.postgres.endpoint)[0]
      PG_DB             = aws_db_instance.postgres.db_name
      PG_USER           = aws_db_instance.postgres.username
      PG_PASSWORD       = "admin123"
    }
  }

  depends_on = [
    data.archive_file.tools_mcp_lambda_files,
    aws_lambda_layer_version.universal_lambda_layer
  ]
}
