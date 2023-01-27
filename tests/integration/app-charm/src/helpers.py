#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Dict

import psycopg2

MYSQL = "mysql"
POSTGRESQL = {"localhost": "postgresql", "microk8s": "postgresql-k8s"}
MONGODB = "mongodb"
DATABASE_NAME = "test_database"
KAFKA = "kafka"
ZOOKEEPER = "zookeeper"


def build_postgresql_connection_string(credentials: Dict[str, str], database_name) -> str:
    """Generate the connection string for PostgreSQL from relation data."""
    username = credentials[POSTGRESQL]["username"]
    password = credentials[POSTGRESQL]["password"]
    endpoints = credentials[POSTGRESQL]["endpoints"]
    host = endpoints.split(",")[0].split(":")[0]
    # Build the complete connection string to connect to the database.
    return f"dbname='{database_name}' user='{username}' host='{host}' password='{password}' connect_timeout=10"


def check_inserted_data_postgresql(credentials: Dict[str, str], database_name: str):
    connection_string = build_postgresql_connection_string(credentials, database_name)
    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        # Read data from previously created database.
        cursor.execute(f"SELECT data FROM {database_name};")
        data = cursor.fetchone()
        assert data[0] == "some data"


def create_table_postgresql(credentials: Dict[str, str], database_name: str):

    connection_string = build_postgresql_connection_string(credentials, database_name)
    # test connection for PostgreSQL with retrieved credentials
    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        # Check that it's possible to write and read data from the database that
        # was created for the application.
        connection.autocommit = True
        cursor.execute(f"DROP TABLE IF EXISTS {database_name};")
        cursor.execute(f"CREATE TABLE {database_name}(data TEXT);")
        cursor.execute(f"INSERT INTO {database_name}(data) VALUES('some data');")
        cursor.execute(f"SELECT data FROM {database_name};")
        data = cursor.fetchone()
        assert data[0] == "some data"


def insert_data_postgresql(credentials: Dict[str, str], database_name: str):

    connection_string = build_postgresql_connection_string(credentials, database_name)
    # test connection for PostgreSQL with retrieved credentials
    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        # Check that it's possible to read data from the database that
        # was created for the application.
        connection.autocommit = True
        cursor.execute(f"INSERT INTO {database_name}(data) VALUES('some data');")
        cursor.execute(f"SELECT data FROM {database_name};")
