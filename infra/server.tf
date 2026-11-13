# The API server: one EC2 instance running Docker Compose (Caddy, API, worker, PostgreSQL).
# The instance is disposable; everything that matters is on the separate data disk.

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*"]
  }
}

locals {
  parameter_path = "/${var.name}/prod"
  server_name    = "${var.name}-api"
}

resource "aws_iam_role" "server" {
  name = "${var.name}-server"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }]
  })
}

# Lets GitHub Actions run the deploy script and lets you open a shell without SSH.
resource "aws_iam_role_policy_attachment" "server_ssm" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "server" {
  name = "app"
  role = aws_iam_role.server.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "PullImages", Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
      {
        Sid      = "PullApiImage"
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = aws_ecr_repository.api.arn
      },
      {
        Sid      = "ReadDeployFiles"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [aws_s3_bucket.deploy.arn, "${aws_s3_bucket.deploy.arn}/*"]
      },
      {
        Sid      = "ReadSettings"
        Effect   = "Allow"
        Action   = ["ssm:GetParametersByPath", "ssm:GetParameters"]
        Resource = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${local.parameter_path}*"]
      },
    ]
  })
}

resource "aws_iam_instance_profile" "server" {
  name = "${var.name}-server"
  role = aws_iam_role.server.name
}

resource "aws_ebs_volume" "data" {
  availability_zone = local.zone
  size              = var.data_volume_size
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "${var.name}-data", Snapshot = "daily" }
  lifecycle {
    prevent_destroy = true # holds the database; remove this line only if you really mean to delete it
  }
}

resource "aws_instance" "server" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.server.id]
  iam_instance_profile        = aws_iam_instance_profile.server.name
  associate_public_ip_address = true
  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    region             = var.region
    data_volume_serial = replace(aws_ebs_volume.data.id, "-", "")
    deploy_bucket      = aws_s3_bucket.deploy.bucket
    ecr_registry       = split("/", aws_ecr_repository.api.repository_url)[0]
    api_domain         = var.api_domain
    parameter_path     = local.parameter_path
  })

  credit_specification {
    cpu_credits = "standard" # never bill for extra CPU credits
  }
  # 1 hop: only the host (deploy.sh, the AWS CLI) can use the instance role. The containers never
  # call AWS, so a compromised container cannot read the secrets in Parameter Store.
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  root_block_device {
    volume_type = "gp3"
    volume_size = 10
    encrypted   = true
  }
  tags = { Name = local.server_name }

  lifecycle {
    ignore_changes = [ami] # don't replace the server whenever Ubuntu publishes a new image
  }
}

resource "aws_volume_attachment" "data" {
  device_name                    = "/dev/sdf"
  volume_id                      = aws_ebs_volume.data.id
  instance_id                    = aws_instance.server.id
  stop_instance_before_detaching = true
}

# Fixed public address for the api DNS record; it moves to a replacement server automatically.
resource "aws_eip" "server" {
  domain     = "vpc"
  instance   = aws_instance.server.id
  depends_on = [aws_internet_gateway.main]
  tags       = { Name = local.server_name }
}

# Daily snapshots of the data disk (Data Lifecycle Manager itself is free).
resource "aws_iam_role" "snapshots" {
  count = var.snapshot_retention_days > 0 ? 1 : 0
  name  = "${var.name}-snapshots"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "dlm.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "snapshots" {
  count      = var.snapshot_retention_days > 0 ? 1 : 0
  role       = aws_iam_role.snapshots[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "data" {
  count              = var.snapshot_retention_days > 0 ? 1 : 0
  description        = "Daily snapshot of ${var.name} data disk"
  execution_role_arn = aws_iam_role.snapshots[0].arn
  state              = "ENABLED"
  policy_details {
    resource_types = ["VOLUME"]
    target_tags    = { Snapshot = "daily" }
    schedule {
      name      = "daily"
      copy_tags = true
      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["18:00"]
      }
      retain_rule {
        count = var.snapshot_retention_days
      }
    }
  }
}

# Non-secret app settings. deploy.sh turns every parameter under this path into the server's .env.
# Secrets (GEMINI_API_KEY, KEY_ENCRYPTION_KEY, JWT_SECRET) are added by you with the AWS CLI, never by Terraform,
# so they never appear in Terraform state.
locals {
  app_settings = {
    APP_ENV                     = "production"
    CORS_ORIGINS                = join(",", concat(["https://${var.domain}"], var.additional_frontend_origins))
    MODEL_CATALOG_JSON          = var.model_catalog_json
    EMBEDDING_PROVIDER          = "gemini"
    EMBEDDING_MODEL             = var.embedding_model
    EMBEDDING_DIMENSIONS        = "1536"
    PROVIDER_RETENTION_VERIFIED = tostring(var.provider_retention_verified)
    PROVIDER_POLICY_URL         = var.provider_policy_url
  }
}

resource "aws_ssm_parameter" "app" {
  for_each = { for k, v in local.app_settings : k => v if v != "" }
  name     = "${local.parameter_path}/${each.key}"
  type     = "String"
  value    = each.value
}
