#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

DATA_INTEGRATOR = "data-integrator"
MYSQL = "mysql"
# POSTGRESQL = "postgresql"
POSTGRESQL = {"localhost": "postgresql", "microk8s": "postgresql-k8s"}
# MONGODB = "mongodb"
MONGODB = {"localhost": "mongodb", "microk8s": "mongodb-k8s"}
DATABASE_NAME = "test_database"
KAFKA = "kafka"
ZOOKEEPER = "zookeeper"
TOPIC_NAME = "test_topic"
EXTRA_USER_ROLES = "producer,consumer,admin"
