#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Literals used by the data-integrator charm."""

from typing import Literal

PEER = "data-integrator-peers"
MYSQL = "mysql"
POSTGRESQL = "postgresql"
MONGODB = "mongodb"
KAFKA = "kafka"

DATABASES = [MYSQL, MONGODB, POSTGRESQL]
STATUSES = Literal["active", "broken", "removed"]
