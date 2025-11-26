terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  name_prefix = "${var.project_name}-${var.deployment_target}"

  tags = merge(
    {
      Project     = var.project_name
      Environment = var.deployment_target
      ManagedBy   = "Terraform"
      Role        = "webapp"
    },
    var.extra_tags,
  )
}

resource "aws_instance" "webapp" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  iam_instance_profile        = var.instance_profile
  vpc_security_group_ids      = var.security_group_ids
  associate_public_ip_address = var.associate_public_ip
  key_name                    = var.ssh_key_name

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size_gb
    encrypted   = true
    tags        = local.tags
  }

  user_data = var.user_data_base64

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  credit_specification {
    cpu_credits = var.instance_type == "t3.micro" ? "standard" : "unlimited"
  }

  monitoring = true

  tags = merge(
    local.tags,
    {
      Name             = "${local.name_prefix}-webapp"
      DeploymentTarget = var.deployment_target
    },
  )
}

resource "aws_ec2_tag" "deployment_branch" {
  resource_id = aws_instance.webapp.id
  key         = "StagingDefaultBranch"
  value       = var.default_branch
}

output "instance_id" {
  value = aws_instance.webapp.id
}

output "public_ip" {
  value = aws_instance.webapp.public_ip
}

output "private_ip" {
  value = aws_instance.webapp.private_ip
}

