resource "aws_apigatewayv2_api" "invoke_agent_api" {
  name          = "${local.application_name}-invoke-agent-api"
  protocol_type = "HTTP"
  description   = "API to invoke the product assistant agent Lambda"
}

resource "aws_apigatewayv2_integration" "invoke_agent" {
  api_id                 = aws_apigatewayv2_api.invoke_agent_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.invoke_agent_lambda_function.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "invoke_agent" {
  api_id    = aws_apigatewayv2_api.invoke_agent_api.id
  route_key = "POST /invoke"
  target    = "integrations/${aws_apigatewayv2_integration.invoke_agent.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.invoke_agent_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_gateway_invoke_agent" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.invoke_agent_lambda_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.invoke_agent_api.execution_arn}/*/*"
}

output "invoke_agent_api_endpoint" {
  description = "Invoke agent API base URL (POST /invoke with body: {\"question\": \"...\"})"
  value       = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/invoke"
}

resource "aws_apigatewayv2_integration" "tools_mcp" {
  api_id                 = aws_apigatewayv2_api.invoke_agent_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.tools_mcp_lambda_function.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "tools_mcp" {
  api_id    = aws_apigatewayv2_api.invoke_agent_api.id
  route_key = "POST /mcp"
  target    = "integrations/${aws_apigatewayv2_integration.tools_mcp.id}"
}

resource "aws_lambda_permission" "api_gateway_tools_mcp" {
  statement_id  = "AllowAPIGatewayInvokeMCP"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.tools_mcp_lambda_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.invoke_agent_api.execution_arn}/*/*"
}

output "tools_mcp_endpoint" {
  description = "MCP server endpoint (POST /mcp)"
  value       = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/mcp"
}
