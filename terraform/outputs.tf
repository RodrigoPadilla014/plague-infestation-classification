output "instance_id" {
  description = "EC2 instance ID — set as CHINCHE_INSTANCE_ID in ec2/config.*.env."
  value       = aws_instance.chinche_training.id
}

output "public_ip" {
  description = "Public IP of the training instance."
  value       = aws_instance.chinche_training.public_ip
}

output "ssh_command" {
  description = "SSH command to connect to the training instance."
  value       = "ssh -i credentials/chinche-training.pem ubuntu@${aws_instance.chinche_training.public_ip}"
}

output "ecr_login_command" {
  description = "Command to authenticate Docker with ECR before pushing the training image."
  value       = "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.${var.aws_region}.amazonaws.com"
}

output "image_push_commands" {
  description = "Commands to tag and push the local training image to ECR."
  value       = <<-EOT
    docker tag chinche-training:latest <AWS_ACCOUNT_ID>.dkr.ecr.${var.aws_region}.amazonaws.com/chinche-training:latest
    docker push <AWS_ACCOUNT_ID>.dkr.ecr.${var.aws_region}.amazonaws.com/chinche-training:latest
  EOT
}
