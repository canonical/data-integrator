#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import PosixPath
from time import sleep

import pytest
from pytest_operator.plugin import OpsTest

from .constants import APP, DATA_INTEGRATOR, DATABASE_NAME, PGBOUNCER, POSTGRESQL
from .helpers import (
    check_secrets_usage_matching_juju_version,
    fetch_action_database,
    fetch_action_get_credentials,
)

logger = logging.getLogger(__name__)


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


async def test_deploy_and_relate_postgresql(ops_test: OpsTest):
    """Test the relation with PostgreSQL and database accessibility."""
    await asyncio.gather(
        ops_test.model.deploy(
            POSTGRESQL[ops_test.cloud_name],
            channel="14/edge",
            application_name=POSTGRESQL[ops_test.cloud_name],
            num_units=1,
            series="jammy",
            trust=True,
        )
    )
    await ops_test.model.wait_for_idle(
        apps=[POSTGRESQL[ops_test.cloud_name]],
        status="active",
    )
    assert ops_test.model.applications[POSTGRESQL[ops_test.cloud_name]].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name]])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for PostgreSQL
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {POSTGRESQL[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        POSTGRESQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {POSTGRESQL[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        POSTGRESQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {POSTGRESQL[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        POSTGRESQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL[ops_test.cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[POSTGRESQL[ops_test.cloud_name], DATA_INTEGRATOR])
    integrator_relation = await ops_test.model.add_relation(
        DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name]
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name]])

    # check if secrets are used on Juju3
    assert await check_secrets_usage_matching_juju_version(
        ops_test,
        ops_test.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )

    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    assert credentials != new_credentials
    logger.info(
        f"Check assessibility of inserted data on {POSTGRESQL[ops_test.cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        POSTGRESQL[ops_test.cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info(f"Unlock (unreleate) {DATA_INTEGRATOR} for the PgBouncer tests")
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL[ops_test.cloud_name]}:database"
    )
    # Ensuring full cleanup of relation traces, avodiing faluire on re-creating it soon
    sleep(3)


async def test_deploy_and_relate_pgbouncer(ops_test: OpsTest):
    """Test the relation with PgBouncer and database accessibility."""
    logger.info(f"Test the relation with {PGBOUNCER[ops_test.cloud_name]}.")
    num_units = 0 if ops_test.cloud_name == "localhost" else 1
    await asyncio.gather(
        ops_test.model.deploy(
            PGBOUNCER[ops_test.cloud_name],
            application_name=PGBOUNCER[ops_test.cloud_name],
            channel="1/edge",
            num_units=num_units,
            series="jammy",
        ),
    )
    await ops_test.model.add_relation(
        PGBOUNCER[ops_test.cloud_name], POSTGRESQL[ops_test.cloud_name]
    )
    await ops_test.model.add_relation(PGBOUNCER[ops_test.cloud_name], DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, PGBOUNCER[ops_test.cloud_name]], status="active"
    )
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    logger.info(f"Get credential for {PGBOUNCER[ops_test.cloud_name]}")
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {PGBOUNCER[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        PGBOUNCER[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {PGBOUNCER[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        PGBOUNCER[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {PGBOUNCER[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        PGBOUNCER[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info("Remove relation and test connection again")
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{PGBOUNCER[ops_test.cloud_name]}:database"
    )

    # Subordinate charm will be removed and wait_for_idle expects the app to have units
    if ops_test.cloud_name == "localhost":
        idle_apps = [DATA_INTEGRATOR]
    else:
        idle_apps = [DATA_INTEGRATOR, PGBOUNCER[ops_test.cloud_name]]

    await ops_test.model.wait_for_idle(apps=idle_apps)
    await ops_test.model.add_relation(DATA_INTEGRATOR, PGBOUNCER[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, PGBOUNCER[ops_test.cloud_name]])

    logger.info("Relate and check the accessibility of the previously created database")
    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(
        f"Check assessibility of inserted data on {PGBOUNCER[ops_test.cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        PGBOUNCER[ops_test.cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
