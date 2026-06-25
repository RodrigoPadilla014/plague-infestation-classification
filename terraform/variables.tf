variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type for the training host."
  type        = string
  default     = "m5.xlarge"
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to SSH into the training instance. Restrict to your IP for production use."
  type        = string
  default     = "0.0.0.0/0"
}
