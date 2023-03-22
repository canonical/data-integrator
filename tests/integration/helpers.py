#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from subprocess import PIPE, check_output
from typing import Dict, Optional

import yaml
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

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
    # Build the complete connection string to connect to the database.
    return f"dbname='{DATABASE_NAME}' user='{username}' host='{host}' password='{password}' connect_timeout=10"


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
        "/var/snap/charmed-kafka/common/log-data"
        if "k8s" not in kafka_unit_name
        else "/var/lib/juju/storage/log-data"
    )

    container = "--container kafka " if "k8s" in kafka_unit_name else ""
    logs = check_output(
        f"JUJU_MODEL={model_full_name} juju ssh {container} {kafka_unit_name} 'find {log_directory}'",
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


async def get_application_relation_data(
    ops_test: OpsTest,
    unit_name: str,
    relation_name: str,
    key: str,
    relation_id: str = None,
) -> Optional[str]:
    """Get relation data for an application.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit
        relation_name: name of the relation to get connection data from
        key: key of data to be retrieved
        relation_id: id of the relation to get connection data from

    Returns:
        the data that was requested or None
            if no data in the relation

    Raises:
        ValueError if it's not possible to get application unit data
            or if there is no data for the particular relation endpoint
            and/or alias.
    """
    raw_data = (await ops_test.juju("show-unit", unit_name))[1]
    if not raw_data:
        raise ValueError(f"no unit info could be grabbed for {unit_name}")
    data = yaml.safe_load(raw_data)
    # Filter the data based on the relation name.
    relation_data = [v for v in data[unit_name]["relation-info"] if v["endpoint"] == relation_name]
    if relation_id:
        # Filter the data based on the relation id.
        relation_data = [v for v in relation_data if v["relation-id"] == relation_id]
    if len(relation_data) == 0:
        raise ValueError(
            f"no relation data could be grabbed on relation with endpoint {relation_name}"
        )
    return relation_data[0]["application-data"].get(key)
