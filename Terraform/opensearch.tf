resource "aws_opensearch_domain" "rag_db" {
  domain_name    = "${local.application_name}-rag-db"
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type  = "t3.small.search"
    instance_count = 1
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 10
  }
}

resource "opensearch_index" "products_main" {
  name      = "products_main"
  index_knn = true
  mappings = jsonencode({
    properties = {
      parent_asin    = { type = "keyword" }
      title          = { type = "text" }
      store          = { type = "keyword" }
      main_category  = { type = "keyword" }
      categories     = { type = "keyword" }
      price          = { type = "float" }
      average_rating = { type = "float" }
      rating_number  = { type = "integer" }
      features       = { type = "text" }
      description    = { type = "text" }
      details        = { type = "object" }
      image_url      = { type = "keyword" }
      embedding = {
        type      = "knn_vector"
        dimension = 1024
        method = {
          name       = "hnsw"
          space_type = "innerproduct"
          engine     = "faiss"
        }
      }
    }
  })

  depends_on    = [aws_opensearch_domain.rag_db]
  force_destroy = true
}
