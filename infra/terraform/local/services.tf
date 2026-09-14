variable "postgres_user" {
  type      = string
  default   = "fraudlatch"
  sensitive = true
}

variable "postgres_password" {
  type      = string
  default   = "fraudlatch"
  sensitive = true
}

variable "postgres_database" {
  type    = string
  default = "fraudlatch"
}

variable "postgres_host_port" {
  type    = number
  default = 55432
}

variable "redis_host_port" {
  type    = number
  default = 6379
}

resource "docker_image" "postgres" {
  name         = "postgres:16"
  keep_locally = true
}

resource "docker_image" "redis" {
  name         = "redis:7"
  keep_locally = true
}

resource "docker_container" "postgres" {
  name  = "${var.project_name}-${var.environment}-postgres"
  image = docker_image.postgres.image_id

  env = [
    "POSTGRES_USER=${var.postgres_user}",
    "POSTGRES_PASSWORD=${var.postgres_password}",
    "POSTGRES_DB=${var.postgres_database}",
  ]

  networks_advanced {
    name = docker_network.app.name
  }

  ports {
    internal = 5432
    external = var.postgres_host_port
  }

  volumes {
    volume_name    = docker_volume.postgres.name
    container_path = "/var/lib/postgresql/data"
  }

  healthcheck {
    test     = ["CMD-SHELL", "pg_isready -U ${var.postgres_user} -d ${var.postgres_database}"]
    interval = "5s"
    timeout  = "3s"
    retries  = 10
  }
}

resource "docker_container" "redis" {
  name    = "${var.project_name}-${var.environment}-redis"
  image   = docker_image.redis.image_id
  command = ["redis-server", "--appendonly", "yes"]

  networks_advanced {
    name = docker_network.app.name
  }

  ports {
    internal = 6379
    external = var.redis_host_port
  }

  volumes {
    volume_name    = docker_volume.redis.name
    container_path = "/data"
  }

  healthcheck {
    test     = ["CMD", "redis-cli", "ping"]
    interval = "5s"
    timeout  = "3s"
    retries  = 10
  }
}

output "database_url" {
  value     = "postgresql+asyncpg://${var.postgres_user}:${var.postgres_password}@localhost:${var.postgres_host_port}/${var.postgres_database}"
  sensitive = true
}

output "redis_url" {
  value = "redis://localhost:${var.redis_host_port}/0"
}
