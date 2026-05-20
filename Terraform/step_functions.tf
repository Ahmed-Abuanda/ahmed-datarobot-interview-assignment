resource "aws_sfn_state_machine" "step_function" {
  name     = "${local.application_name}-data-processing-step-function"
  role_arn = aws_iam_role.step_functions_role.arn

  definition = jsonencode({
    Comment = "Run text embedder on the json_file input"
    StartAt = "TextEmbedder"
    States = {
      TextEmbedder = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.text_embedder_lambda_function.function_name
          Payload = {
            "json_file.$" = "$.json_file"
          }
        }
        ResultSelector = {
          "text_embedder_result.$" = "$.Payload"
        }
        End = true
      }
    }
  })

  depends_on = [
    aws_iam_role_policy.step_functions_invoke_lambda,
    aws_lambda_function.text_embedder_lambda_function
  ]
}
