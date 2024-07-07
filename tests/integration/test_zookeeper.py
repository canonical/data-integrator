#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from .constants import APP, DATA_INTEGRATOR, DATABASE_NAME, ZOOKEEPER
from .helpers import (
    check_secrets_usage_matching_juju_version,
    fetch_action_database,
    fetch_action_get_credentials,
)

logger = logging.getLogger(__name__)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest, app_charm: PosixPath, data_integrator_charm: PosixPath):
    if (await ops_test.model.get_status()).model.version.startswith("3.1."):
        pytest.skip("Test is incompatible with Juju 3.1")

    await asyncio.gather(
        ops_test.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        ),
        ops_test.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"

    # config database name

    config = {"database-name": f"/{DATABASE_NAME}"}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"


@pytest.mark.group(1)
async def test_deploy_and_relate_zookeeper(ops_test: OpsTest, cloud_name: str):
    """Test the relation with ZooKeeper and database accessibility."""
    if (await ops_test.model.get_status()).model.version.startswith("3.1."):
        pytest.skip("Test is incompatible with Juju 3.1")

    provider_name = ZOOKEEPER[cloud_name]

    await asyncio.gather(
        ops_test.model.deploy(
            provider_name,
            channel="3/edge",
            application_name=provider_name,
            num_units=1,
            series="jammy",
            trust=True,
        )
    )
    await ops_test.model.wait_for_idle(apps=[ZOOKEEPER[cloud_name]], wait_for_active=True)
    assert ops_test.model.applications[provider_name].status == "active"
    integrator_relation = await ops_test.model.add_relation(DATA_INTEGRATOR, provider_name)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, provider_name])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # check if secrets are used on Juju3
    assert await check_secrets_usage_matching_juju_version(
        ops_test,
        ops_test.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )

    # get credential for ZooKeeper
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info(f"Create zNode on {ZOOKEEPER[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        ZOOKEEPER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert zNode on {ZOOKEEPER[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        ZOOKEEPER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {ZOOKEEPER[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        ZOOKEEPER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    #  remove relation and test connection again
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{ZOOKEEPER[cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[ZOOKEEPER[cloud_name], DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, ZOOKEEPER[cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, ZOOKEEPER[cloud_name]])

    # join with another relation and check the accessibility of the previously created database
    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(
        f"Check assessibility of inserted data on {ZOOKEEPER[cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        ZOOKEEPER[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
