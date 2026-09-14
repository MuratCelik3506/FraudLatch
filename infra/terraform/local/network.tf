resource "docker_network" "app" {
  name = "${var.project_name}-${var.environment}"
  labels {
    label = "com.fraudlatch.project"
    value = var.project_name
  }
  labels {
    label = "com.fraudlatch.environment"
    value = var.environment
  }
}

resource "docker_volume" "postgres" {
  name = "${var.project_name}-${var.environment}-postgres"
}

resource "docker_volume" "redis" {
  name = "${var.project_name}-${var.environment}-redis"
}

resource "docker_volume" "prometheus" {
  name = "${var.project_name}-${var.environment}-prometheus"
}

resource "docker_volume" "grafana" {
  name = "${var.project_name}-${var.environment}-grafana"
}
