output "network_name" {
  value       = docker_network.app.name
  description = "Shared local Docker network."
}

output "postgres_volume" {
  value = docker_volume.postgres.name
}

output "redis_volume" {
  value = docker_volume.redis.name
}

output "prometheus_volume" {
  value = docker_volume.prometheus.name
}

output "grafana_volume" {
  value = docker_volume.grafana.name
}
