resource "aws_security_group" "postgres" {
  name = "${local.application_name}-postgres-sg"

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "postgres" {
  identifier             = "${local.application_name}-postgres"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = "datarobot"
  username               = "appuser"
  password               = "admin123"
  publicly_accessible    = true
  skip_final_snapshot    = true
  vpc_security_group_ids = [aws_security_group.postgres.id]
}

output "postgres_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

resource "null_resource" "apply_schema" {
  triggers = {
    schema_hash = filemd5("${path.root}/../Resources/schema.sql")
    db_endpoint = aws_db_instance.postgres.endpoint
  }

  provisioner "local-exec" {
    command = <<-EOT
      for i in $(seq 1 30); do
        PGPASSWORD=admin123 psql \
          "host=${split(":", aws_db_instance.postgres.endpoint)[0]} port=5432 dbname=${aws_db_instance.postgres.db_name} user=${aws_db_instance.postgres.username} connect_timeout=5" \
          -f ${path.root}/../Resources/schema.sql && exit 0
        echo "Postgres not ready yet (attempt $i/30), waiting 10s..."
        sleep 10
      done
      echo "Postgres still not reachable after 5 minutes" >&2
      exit 1
    EOT
  }

  depends_on = [aws_db_instance.postgres]
}
