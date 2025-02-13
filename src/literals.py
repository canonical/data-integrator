#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Literals used by the data-integrator charm."""

PEER = "data-integrator-peers"
MYSQL = "mysql"
POSTGRESQL = "postgresql"
MONGODB = "mongodb"
MONGOS = "mongos"
KAFKA = "kafka"
ZOOKEEPER = "zookeeper"
OPENSEARCH = "opensearch"
KYUUBI = "kyuubi"

DATABASES = [MYSQL, MONGODB, POSTGRESQL, MONGOS, ZOOKEEPER, KYUUBI]
