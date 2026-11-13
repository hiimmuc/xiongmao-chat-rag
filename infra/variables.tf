variable "region" {
  description = "Region for the server and buckets. us-east-1 is the cheapest for EC2."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Prefix for resource names and the SSM parameter path."
  type        = string
  default     = "xiongmao"
}

variable "domain" {
  description = "Frontend domain (CloudFront)."
  type        = string
  default     = "xiong-mao.net"
}

variable "api_domain" {
  description = "Backend domain (EC2 + Caddy)."
  type        = string
  default     = "api.xiong-mao.net"
}

variable "github_repository" {
  description = "owner/name of the GitHub repository allowed to deploy."
  type        = string
  default     = "hiimmuc/xiongmao-chat-rag"
}

variable "github_branch" {
  description = "Only pushes to this branch can deploy."
  type        = string
  default     = "main"
}

variable "create_github_oidc_provider" {
  description = "Set false if the AWS account already has the token.actions.githubusercontent.com provider."
  type        = bool
  default     = true
}

variable "instance_type" {
  description = "Burstable Graviton (arm64) type; CI builds arm64 images. t4g.small doubles memory for ~$6 more."
  type        = string
  default     = "t4g.micro"
  validation {
    condition     = can(regex("^t4g\\.", var.instance_type))
    error_message = "Use a t4g instance type (arm64, burstable)."
  }
}

variable "data_volume_size" {
  description = "GiB for the data disk (database, uploads, certificates)."
  type        = number
  default     = 10
}

variable "snapshot_retention_days" {
  description = "Daily snapshots of the data disk to keep; 0 turns snapshots off."
  type        = number
  default     = 7
}

variable "model_catalog_json" {
  description = "Models offered in the picker. An id is stored with chat history: never reuse one for another model."
  type        = string
  default     = "[{\"id\":\"gemini-3.5-flash-lite\",\"provider\":\"gemini\",\"label\":\"Gemini 3.5 Flash-Lite\",\"api_model\":\"gemini-3.5-flash-lite\",\"context_tokens\":128000},{\"id\":\"gemini-3.6-flash\",\"provider\":\"gemini\",\"label\":\"Gemini 3.6 Flash\",\"api_model\":\"gemini-3.6-flash\",\"context_tokens\":128000}]"
}

variable "embedding_model" {
  description = "Gemini embedding model used for every document; changing it requires re-indexing."
  type        = string
  default     = "gemini-embedding-001"
}

variable "provider_retention_verified" {
  description = "Set true once you have reviewed Gemini's data processing and retention terms. Models stay hidden until then."
  type        = bool
  default     = false
}

variable "provider_policy_url" {
  description = "Public link to those terms, shown in Settings. Optional."
  type        = string
  default     = ""
}

variable "additional_frontend_origins" {
  description = "Extra exact origins allowed to call the API (CORS), e.g. a preview site."
  type        = list(string)
  default     = []
  validation {
    condition     = alltrue([for o in var.additional_frontend_origins : can(regex("^https?://[^/*]+$", o))])
    error_message = "Use exact origins without a path, trailing slash or wildcard."
  }
}
