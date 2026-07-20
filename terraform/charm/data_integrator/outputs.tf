# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

output "application" {
  description = "Object representing the deployed application."
  value       = juju_application.data_integrator
}

output "offers" {
  description = "Map of all offers exposed by the single charm."
  value       = {}
}

output "provides" {
  description = "Provides endpoints."
  value = {
    mongos = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "mongos"
    }
  }
}

output "requires" {
  description = "Requires endpoints."
  value = {
    cassandra = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "cassandra"
    }
    etcd = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "etcd"
    }
    kafka = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "kafka"
    }
    kyuubi = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "kyuubi"
    }
    mongodb = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "mongodb"
    }
    mysql = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "mysql"
    }
    opensearch = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "opensearch"
    }
    postgresql = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "postgresql"
    }
    valkey = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "valkey"
    }
    zookeeper = {
      kind     = "endpoint"
      name     = juju_application.data_integrator.name
      endpoint = "zookeeper"
    }
  }
}
