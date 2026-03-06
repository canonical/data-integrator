#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from .constants import (
    APP,
    DATA_INTEGRATOR,
    CASSANDRA_EXTRA_USER_ROLES,
    CASSANDRA,
    KEYSPACE_NAME,
)
from .helpers import check_logs, fetch_action_database, fetch_action_get_credentials, fetch_action_kafka

logger = logging.getLogger(__name__)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest, app_charm: PosixPath, data_integrator_charm: PosixPath):
    await asyncio.gather(
        ops_test.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        ),
        ops_test.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP], idle_period=30)
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"

    config = {"topic-name": KEYSPACE_NAME, "extra-user-roles": CASSANDRA_EXTRA_USER_ROLES}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/blocked status for relation
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR],
        raise_on_error=False,
        status="blocked",
        idle_period=120,
    )
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_deploy_and_relate_cassandra(ops_test: OpsTest, cloud_name: str):
    """Test the relation with Kafka and the correct production and consumption of messagges."""
    await asyncio.gather(
        ops_test.model.deploy(
            CASSANDRA[cloud_name],
            channel="5/edge",
            application_name=CASSANDRA[cloud_name],
            num_units=1,
        ),
    )

    await ops_test.model.wait_for_idle(apps=[CASSANDRA[cloud_name]], timeout=1000, status="active")

    await ops_test.model.add_relation(CASSANDRA[cloud_name], DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(
        apps=[CASSANDRA[cloud_name], DATA_INTEGRATOR],
        timeout=2000,
        idle_period=30,
        status="active",
    )

@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_data_read_write_on_cassandra(ops_test: OpsTest, cloud_name: str):
    """Test the database accessibility."""    
    # get credential for Cassandra
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info(f"Create table on {CASSANDRA}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        CASSANDRA[cloud_name],
        json.dumps(credentials),
        KEYSPACE_NAME,
    )
    assert result["ok"]    

    logger.info(f"Insert rows to table on {CASSANDRA}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        CASSANDRA[cloud_name],
        json.dumps(credentials),
        KEYSPACE_NAME,
    )
    assert result["ok"]

    logger.info(f"Check assessibility of inserted data on {CASSANDRA}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        CASSANDRA[cloud_name],
        json.dumps(credentials),
        KEYSPACE_NAME,
    )
    assert result["ok"]

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:cassandra", f"{CASSANDRA[cloud_name]}:cassandra-client"
    )
    await ops_test.model.wait_for_idle(apps=[CASSANDRA[cloud_name], DATA_INTEGRATOR])

    await ops_test.model.add_relation(DATA_INTEGRATOR, CASSANDRA[cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, CASSANDRA[cloud_name]])

    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # test that different credentials are provided
    assert credentials != new_credentials
    
    logger.info(f"Check assessibility of inserted data on {CASSANDRA} with new credentials")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        CASSANDRA[cloud_name],
        json.dumps(new_credentials),
        KEYSPACE_NAME,
    )
    assert result["ok"]
