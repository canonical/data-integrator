#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

DATA_INTEGRATOR = "data-integrator"

TLS_CERTIFICATES_APP_NAME = "self-signed-certificates"

MYSQL = {"localhost": "mysql", "k8s": "mysql-k8s"}
MYSQL_ROUTER = {"localhost": "mysql-router", "k8s": "mysql-router-k8s"}
POSTGRESQL = {"localhost": "postgresql", "k8s": "postgresql-k8s"}
PGBOUNCER = {"localhost": "pgbouncer", "k8s": "pgbouncer-k8s"}
MONGODB = {"localhost": "mongodb", "k8s": "mongodb-k8s"}
DATABASE_NAME = "test_database"

KAFKA = {"localhost": "kafka", "k8s": "kafka-k8s"}
ZOOKEEPER = {"localhost": "zookeeper", "k8s": "zookeeper-k8s"}
TOPIC_NAME = "test_topic"
KAFKA_EXTRA_USER_ROLES = "producer,consumer,admin"

OPENSEARCH = {"localhost": "opensearch"}
INDEX_NAME = "albums"
OPENSEARCH_EXTRA_USER_ROLES = "default"

KYUUBI = {"k8s": "kyuubi-k8s"}
ETCD = {"localhost": "charmed-etcd"}
APP = "app"

CASSANDRA = {"localhost": "cassandra"}
KEYSPACE_NAME = "test_ks"
CASSANDRA_EXTRA_USER_ROLES = "ALTER,AUTHORIZE,DROP,MODIFY,SELECT,CREATE"

VALKEY = "valkey"
VALKEY_KEY_PREFIX = "client_application:"
