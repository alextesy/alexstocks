variable "aws_region" {
  description = "AWS region for the web app host"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project tag prefix"
  type        = string
  default     = "market-pulse"
}

variable "deployment_target" {
  description = "Environment label (production or staging)"
  type        = string
  default     = "staging"
}

variable "ami_id" {
  description = "AMI ID captured from the production EC2 instance"
  type        = string
}

variable "instance_type" {
  description = "Instance type for the web app"
  type        = string
  default     = "t3.medium"
}

variable "subnet_id" {
  description = "Subnet where the instance will be placed"
  type        = string
}

variable "security_group_ids" {
  description = "Security groups that allow SSH + HTTP(S) + DB access"
  type        = list(string)
}

variable "associate_public_ip" {
  description = "Whether to attach a public IP"
  type        = bool
  default     = true
}

variable "ssh_key_name" {
  description = "EC2 key pair for adhoc SSH access"
  type        = string
}

variable "instance_profile" {
  description = "IAM instance profile used by the web app"
  type        = string
}

variable "root_volume_size_gb" {
  description = "Size of the root EBS volume"
  type        = number
  default     = 40
}

variable "default_branch" {
  description = "Branch to check out when staging boots (for tagging/reference)"
  type        = string
  default     = "develop"
}

variable "user_data_base64" {
  description = "Optional base64-encoded user data to run at boot (e.g., git pull)"
  type        = string
  default     = ""
}

variable "extra_tags" {
  description = "Optional extra tags to apply to the instance"
  type        = map(string)
  default     = {}
}

