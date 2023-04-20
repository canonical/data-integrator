#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from subprocess import PIPE, check_output
from typing import Dict

from juju.unit import Unit

from .constants import DATABASE_NAME, POSTGRESQL

logger = logging.getLogger(__name__)


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
    port = endpoints.split(",")[0].split(":")[1]
    # Build the complete connection string to connect to the database.
    return f"dbname='{DATABASE_NAME}' user='{username}' host='{host}' port='{port}' password='{password}' connect_timeout=10"


async def fetch_action_database(
    unit: Unit, action_name: str, product: str, credentials: str, database_name: str
) -> Dict:
    """Helper to run an action to execute commands with databases.

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
    return result.results


async def fetch_action_kafka(
    unit: Unit, action_name: str, product: str, credentials: str, topic_name: str
) -> Dict:
    """Helper to run an action to test Kafka.

    Args:
        unit: The juju unit on which to run the action
        action_name: name of the action
        product: the name of the product
        credentials: credentials used to connect
        topic_name: name of the database
    Returns:
        The result of the action
    """
    parameters = {"product": product, "credentials": credentials, "topic-name": topic_name}
    action = await unit.run_action(action_name=action_name, **parameters)
    result = await action.wait()
    return result.results


def check_logs(model_full_name: str, kafka_unit_name: str, topic: str) -> None:
    """Check that logs are written for a Kafka topic.

    Args:
        model_full_name: the full name of the model
        kafka_unit_name: the kafka unit to checks logs on
        topic: the desired topic to produce to
    Raises:
        KeyError: if missing relation data
        AssertionError: if logs aren't found for desired topic
    """
    log_directory = (
        "/var/snap/charmed-kafka/common/var/lib/kafka/data"
        if "k8s" not in kafka_unit_name
        else "/var/lib/juju/storage/log-data"
    )

    container = "--container kafka " if "k8s" in kafka_unit_name else ""
    sudo = "sudo -i " if "k8s" not in kafka_unit_name else ""
    logs = check_output(
        f"JUJU_MODEL={model_full_name} juju ssh {container} {kafka_unit_name} {sudo} 'find {log_directory}'",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    ).splitlines()

    logger.debug(f"{logs=}")
    passed = False
    for log in logs:
        if topic and "index" in log:
            passed = True
            break

    assert passed, "logs not found"
