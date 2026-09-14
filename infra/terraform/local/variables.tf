variable "project_name" {
  type        = string
  description = "Prefix used for local Docker resources."
  default     = "fraudlatch"
}

variable "environment" {
  type        = string
  description = "Local environment label."
  default     = "local"
}
