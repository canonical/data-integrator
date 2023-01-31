#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Dict

from juju.unit import Unit

from tests.integration.constants import DATABASE_NAME, POSTGRESQL


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


def build_postgresql_connection_string(credentials: Dict[str, str]) -> str:
    """Generate the connection string for PostgreSQL from relation data."""
    username = credentials[POSTGRESQL]["username"]
    password = credentials[POSTGRESQL]["password"]
    endpoints = credentials[POSTGRESQL]["endpoints"]
    host = endpoints.split(",")[0].split(":")[0]
    # Build the complete connection string to connect to the database.
    return f"dbname='{DATABASE_NAME}' user='{username}' host='{host}' password='{password}' connect_timeout=10"


async def fetch_action_database(
    unit: Unit, action_name: str, product: str, credentials: str, database_name: str
) -> Dict:
    """Helper to run an action to sync credentials.

    Args:
        unit: The juju unit on which to run the action
        action_name: name of the action
        product: the name of the product
        credentials: credentials used to connect
        database_name: name of the database
    Returns:
        The result of the action
    """
    parameters = {"product": product, "credentials": credentials, "database-name": database_name}
    action = await unit.run_action(action_name=action_name, **parameters)
    result = await action.wait()
    return result
