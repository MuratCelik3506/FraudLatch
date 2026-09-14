resource "docker_image" "prometheus" {
  name         = "prom/prometheus:v3.5.0"
  keep_locally = true
}

resource "docker_image" "grafana" {
  name         = "grafana/grafana:12.1.0"
  keep_locally = true
}

resource "docker_container" "prometheus" {
  name  = "${var.project_name}-${var.environment}-prometheus"
  image = docker_image.prometheus.image_id

  networks_advanced { name = docker_network.app.name }
  ports { internal = 9090 external = 9090 }
  volumes {
    volume_name    = docker_volume.prometheus.name
    container_path = "/prometheus"
  }
  volumes {
    host_path      = "${path.root}/../../../monitoring/prometheus/prometheus.yml"
    container_path = "/etc/prometheus/prometheus.yml"
    read_only      = true
  }
  command = ["--config.file=/etc/prometheus/prometheus.yml"]
  healthcheck {
    test     = ["CMD", "wget", "--spider", "-q", "http://localhost:9090/-/ready"]
    interval = "10s"
    timeout  = "5s"
    retries  = 10
  }
}

resource "docker_container" "grafana" {
  name  = "${var.project_name}-${var.environment}-grafana"
  image = docker_image.grafana.image_id

  networks_advanced { name = docker_network.app.name }
  ports { internal = 3000 external = 3000 }
  volumes {
    volume_name    = docker_volume.grafana.name
    container_path = "/var/lib/grafana"
  }
  volumes {
    host_path      = "${path.root}/../../../monitoring/grafana/provisioning"
    container_path = "/etc/grafana/provisioning"
    read_only      = true
  }
  volumes {
    host_path      = "${path.root}/../../../monitoring/grafana/dashboards"
    container_path = "/var/lib/grafana/dashboards"
    read_only      = true
  }
  healthcheck {
    test     = ["CMD", "wget", "--spider", "-q", "http://localhost:3000/api/health"]
    interval = "10s"
    timeout  = "5s"
    retries  = 10
  }
}

output "prometheus_url" {
  value = "http://localhost:9090"
}

output "grafana_url" {
  value = "http://localhost:3000"
}
