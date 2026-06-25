terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}


# ── Existing resources (referenced, not managed) ──────────────────────────────

data "aws_iam_instance_profile" "ec2_s3_access" {
  name = "EC2-S3-Access"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}


# ── Key pair ──────────────────────────────────────────────────────────────────

resource "tls_private_key" "chinche" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "chinche" {
  key_name   = "chinche-training-key"
  public_key = tls_private_key.chinche.public_key_openssh
}

resource "local_sensitive_file" "pem" {
  content         = tls_private_key.chinche.private_key_openssh
  filename        = "${path.module}/../credentials/chinche-training.pem"
  file_permission = "0600"
}


# ── Security group ────────────────────────────────────────────────────────────

resource "aws_security_group" "chinche_training" {
  name        = "chinche-training-sg"
  description = "chinche training instance - SSH inbound, all outbound"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "chinche-training-sg"
    Project = "chinche"
  }
}


# ── EC2 instance ──────────────────────────────────────────────────────────────

resource "aws_instance" "chinche_training" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.chinche.key_name
  vpc_security_group_ids = [aws_security_group.chinche_training.id]
  iam_instance_profile   = data.aws_iam_instance_profile.ec2_s3_access.name

  root_block_device {
    volume_size = 50
    volume_type = "gp3"
    encrypted   = true
  }

  # Installs Docker and AWS CLI v2 on first boot.
  # awscli package was removed from Ubuntu 24.04 apt repos; use the official installer instead.
  # usermod takes effect on next login.
  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail
    apt-get update -y
    apt-get install -y docker.io curl unzip
    systemctl enable docker
    systemctl start docker
    usermod -aG docker ubuntu
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    unzip -q /tmp/awscliv2.zip -d /tmp
    /tmp/aws/install
    rm -rf /tmp/awscliv2.zip /tmp/aws
  EOF

  tags = {
    Name    = "chinche-training"
    Project = "chinche"
  }
}
