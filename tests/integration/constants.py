#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

DATA_INTEGRATOR = "data-integrator"

TLS_CERTIFICATES_APP_NAME = "tls-certificates-operator"

MYSQL = {"localhost": "mysql", "microk8s": "mysql-k8s"}
POSTGRESQL = {"localhost": "postgresql", "microk8s": "postgresql-k8s"}
PGBOUNCER = {"localhost": "pgbouncer", "microk8s": "pgbouncer-k8s"}
MONGODB = {"localhost": "mongodb", "microk8s": "mongodb-k8s"}
DATABASE_NAME = "test_database"

KAFKA = {"localhost": "kafka", "microk8s": "kafka-k8s"}
ZOOKEEPER = {"localhost": "zookeeper", "microk8s": "zookeeper-k8s"}
TOPIC_NAME = "test_topic"
EXTRA_USER_ROLES = "producer,consumer,admin"

OPENSEARCH = {"localhost": "opensearch"}
INDEX_NAME = "albums"
OPENSEARCH_EXTRA_USER_ROLES = "default"

APP = "app"
