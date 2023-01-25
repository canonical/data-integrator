#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import itertools
from typing import Dict, List, Tuple

from connector import MysqlConnector
from juju.unit import Unit

from tests.integration.constants import DATABASE_NAME, MYSQL, POSTGRESQL


async def fetch_action_get_credentials(unit: Unit) -> Dict:
    """Helper to run an action to fetch connection info.

    Args:
        unit: The juju unit on which to run the get_credentials action for credentials
    Returns:
        A dictionary with the username, password and access info for the service
    """
    action = await unit.run_action(action_name="get-credentials")
    result = await action.wait()
    return result.results


async def execute_commands_on_mysql_unit(
    unit_address: str,
    username: str,
    password: str,
    queries: List[str],
    commit: bool = False,
) -> List:
    """Execute given MySQL queries on a unit.

    Args:
        unit_address: The public IP address of the unit to execute the queries on
        username: The MySQL username
        password: The MySQL password
        queries: A list of queries to execute
        commit: A keyword arg indicating whether there are any writes queries
    Returns:
        A list of rows that were potentially queried
    """
    config = {
        "user": username,
        "password": password,
        "host": unit_address,
        "raise_on_warnings": False,
    }

    with MysqlConnector(config, commit) as cursor:
        for query in queries:
            cursor.execute(query)
        output = list(itertools.chain(*cursor.fetchall()))

    return output


def build_postgresql_connection_string(credentials: Dict[str, str]) -> str:
    """Generate the connection string for PostgreSQL from relation data."""
    username = credentials[POSTGRESQL]["username"]
    password = credentials[POSTGRESQL]["password"]
    endpoints = credentials[POSTGRESQL]["endpoints"]
    host = endpoints.split(",")[0].split(":")[0]
    # Build the complete connection string to connect to the database.
    return f"dbname='{DATABASE_NAME}' user='{username}' host='{host}' password='{password}' connect_timeout=10"


def create_table_mysql(self, cursor, table_name: str) -> None:
    """Create a table in the database."""
    cursor.execute(
        (
            f"CREATE TABLE IF NOT EXISTS {table_name} ("
            "id SMALLINT not null auto_increment,"
            "username VARCHAR(255),"
            "password VARCHAR(255),"
            "endpoints VARCHAR(255),"
            "version VARCHAR(255),"
            "read_only_endpoints VARCHAR(255),"
            "PRIMARY KEY (id))"
        )
    )


def insert_data_mysql(
    cursor,
    database: str,
    username: str,
    password: str,
    endpoints: str,
    version: str,
    read_only_endpoints: str,
) -> None:
    """Insert test data in the database."""
    cursor.execute(
        " ".join(
            (
                f"INSERT INTO {database} (",
                "username, password, endpoints, version, read_only_endpoints)",
                "VALUES (%s, %s, %s, %s, %s)",
            )
        ),
        (username, password, endpoints, version, read_only_endpoints),
    )


def read_data_mysql(cursor, user: str, database: str) -> List[Tuple]:
    """Read data from the specified database."""
    cursor.execute(f"SELECT * FROM app_data where username = '{user}'")
    return cursor.fetchall()


def check_my_sql_data(rows: List[Tuple], credentials: Dict):
    """Check if the correspondace of mysql table values."""
    first_row = rows[0]
    # username, password, endpoints, version, ro-endpoints
    assert first_row[1] == credentials[MYSQL]["username"]
    assert first_row[2] == credentials[MYSQL]["password"]
    assert first_row[3] == credentials[MYSQL]["endpoints"]
    assert first_row[4] == credentials[MYSQL]["version"]
    assert first_row[5] == credentials[MYSQL]["read-only-endpoints"]
