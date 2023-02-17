#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from tests.integration.constants import (
    APP,
    DATA_INTEGRATOR,
    DATABASE_NAME,
    MYSQL,
    MYSQL_ROUTER,
)
from tests.integration.helpers import (
    fetch_action_database,
    fetch_action_get_credentials,
)

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, app_charm: PosixPath):
    data_integrator_charm = await ops_test.build_charm(".")
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


async def test_deploy_and_relate_mysql(ops_test: OpsTest):
    """Test the relation with MySQL and database accessibility."""
    await asyncio.gather(
        ops_test.model.deploy(
            MYSQL[ops_test.cloud_name],
            channel="edge",
            application_name=MYSQL[ops_test.cloud_name],
            num_units=1,
            series="jammy",
            trust=True,
        )
    )
    await ops_test.model.wait_for_idle(apps=[MYSQL[ops_test.cloud_name]], wait_for_active=True)
    assert ops_test.model.applications[MYSQL[ops_test.cloud_name]].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, MYSQL[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL[ops_test.cloud_name]])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for MYSQL
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info(f"Create table on {MYSQL[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        MYSQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {MYSQL[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        MYSQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {MYSQL[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MYSQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    #  remove relation and test connection again
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{MYSQL[ops_test.cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MYSQL[ops_test.cloud_name], DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, MYSQL[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL[ops_test.cloud_name]])

    # join with another relation and check the accessibility of the previously created database
    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(
        f"Check assessibility of inserted data on {MYSQL[ops_test.cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MYSQL[ops_test.cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{MYSQL[ops_test.cloud_name]}:database"
    )

async def test_deploy_and_relate_mysql_router(ops_test: OpsTest):
    """Test the relation with MySQL and database accessibility."""
    channel = "dpe/edge" if ops_test.cloud_name == "localhost" else "edge"
    await asyncio.gather(
        ops_test.model.deploy(
            MYSQL_ROUTER[ops_test.cloud_name],
            channel=channel,
            application_name=MYSQL_ROUTER[ops_test.cloud_name],
            num_units=1,
            series="focal",
            trust=True,
        )
    )
    await ops_test.model.wait_for_idle(apps=[MYSQL_ROUTER[ops_test.cloud_name]], wait_for_active=True)
    assert ops_test.model.applications[MYSQL_ROUTER[ops_test.cloud_name]].status == "waiting"

    
    await ops_test.model.add_relation(MYSQL[ops_test.cloud_name], MYSQL_ROUTER[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[MYSQL[ops_test.cloud_name], MYSQL[ops_test.cloud_name]], status="active")

    await ops_test.model.add_relation(DATA_INTEGRATOR, MYSQL_ROUTER[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL[ops_test.cloud_name]])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for MYSQL
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info(f"Create table on {MYSQL_ROUTER[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        MYSQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {MYSQL_ROUTER[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        MYSQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {MYSQL_ROUTER[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MYSQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    #  remove relation and test connection again
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{MYSQL_ROUTER[ops_test.cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MYSQL_ROUTER[ops_test.cloud_name], DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, MYSQL_ROUTER[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL_ROUTER[ops_test.cloud_name]])

    # join with another relation and check the accessibility of the previously created database
    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(
        f"Check assessibility of inserted data on {MYSQL_ROUTER[ops_test.cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MYSQL[ops_test.cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{MYSQL_ROUTER[ops_test.cloud_name]}:database"
    )

