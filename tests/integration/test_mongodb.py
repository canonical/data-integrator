#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from .constants import APP, DATA_INTEGRATOR, DATABASE_NAME, MONGODB
from .helpers import (
    check_secrets_usage_matching_juju_version,
    fetch_action_database,
    fetch_action_get_credentials,
)

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
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"

    # config database name

    config = {"database-name": DATABASE_NAME}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"


@pytest.mark.group(1)
async def test_deploy_and_relate_mongodb(ops_test: OpsTest, cloud_name: str):
    """Test the relation with MongoDB and database accessibility."""
    channel = "5/edge" if cloud_name == "localhost" else "edge"
    await asyncio.gather(
        ops_test.model.deploy(
            MONGODB[cloud_name],
            channel=channel,
            application_name=MONGODB[cloud_name],
            num_units=1,
            series="jammy",
        )
    )
    await ops_test.model.wait_for_idle(apps=[MONGODB[cloud_name]], wait_for_active=True)
    assert ops_test.model.applications[MONGODB[cloud_name]].status == "active"
    integrator_relation = await ops_test.model.add_relation(DATA_INTEGRATOR, MONGODB[cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB[cloud_name]])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # check if secrets are used on Juju3
    assert await check_secrets_usage_matching_juju_version(
        ops_test,
        ops_test.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )

    # get credential for MongoDB
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {MONGODB[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        MONGODB[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {MONGODB[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        MONGODB[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {MONGODB[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MONGODB[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    # drop relation and get new credential for the same collection
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB[cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MONGODB[cloud_name], DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, MONGODB[cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB[cloud_name]])

    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # test that different credentials are provided
    assert credentials != new_credentials

    logger.info(
        f"Check assessibility of inserted data on {MONGODB[cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MONGODB[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB[cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MONGODB[cloud_name], DATA_INTEGRATOR])
