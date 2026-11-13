terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # State is kept locally in infra/terraform.tfstate (git-ignored). Back that file up.
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = var.name }
  }
}

# CloudFront only accepts certificates issued in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = { Project = var.name }
  }
}

data "aws_caller_identity" "current" {}
