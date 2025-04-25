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
from .juju_ import has_secrets

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
async def test_deploy_and_relate_postgresql(ops_test: OpsTest, cloud_name: str):
    """Test the relation with PostgreSQL and database accessibility."""
    channel = "16/edge" if has_secrets else "14/edge"
    series = "noble" if has_secrets else "jammy"
    await asyncio.gather(
        ops_test.model.deploy(
            POSTGRESQL[cloud_name],
            channel=channel,
            application_name=POSTGRESQL[cloud_name],
            num_units=1,
            series=series,
            trust=True,
        )
    )
    await ops_test.model.wait_for_idle(
        apps=[POSTGRESQL[cloud_name]],
        status="active",
        timeout=1000,
    )
    assert ops_test.model.applications[POSTGRESQL[cloud_name]].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL[cloud_name])
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, POSTGRESQL[cloud_name]], status="active"
    )
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for PostgreSQL
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {POSTGRESQL[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        POSTGRESQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {POSTGRESQL[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        POSTGRESQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {POSTGRESQL[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        POSTGRESQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL[cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[POSTGRESQL[cloud_name], DATA_INTEGRATOR])
    integrator_relation = await ops_test.model.add_relation(
        DATA_INTEGRATOR, POSTGRESQL[cloud_name]
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL[cloud_name]])

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
        f"Check assessibility of inserted data on {POSTGRESQL[cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        POSTGRESQL[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info(f"Unlock (unreleate) {DATA_INTEGRATOR} for the PgBouncer tests")
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL[cloud_name]}:database"
    )
    # Ensuring full cleanup of relation traces, avodiing faluire on re-creating it soon
    sleep(3)


@pytest.mark.group(1)
async def test_deploy_and_relate_pgbouncer(ops_test: OpsTest, cloud_name: str):
    """Test the relation with PgBouncer and database accessibility."""
    logger.info(f"Test the relation with {PGBOUNCER[cloud_name]}.")
    num_units = 0 if cloud_name == "localhost" else 1
    await asyncio.gather(
        ops_test.model.deploy(
            PGBOUNCER[cloud_name],
            application_name=PGBOUNCER[cloud_name],
            channel="1/edge",
            num_units=num_units,
            series="jammy",
            trust=True,
        ),
    )
    await ops_test.model.add_relation(PGBOUNCER[cloud_name], POSTGRESQL[cloud_name])
    await ops_test.model.add_relation(PGBOUNCER[cloud_name], DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, PGBOUNCER[cloud_name]], status="active"
    )
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    logger.info(f"Get credential for {PGBOUNCER[cloud_name]}")
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {PGBOUNCER[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        PGBOUNCER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {PGBOUNCER[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        PGBOUNCER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {PGBOUNCER[cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        PGBOUNCER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info("Remove relation and test connection again")
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{PGBOUNCER[cloud_name]}:database"
    )

    # Subordinate charm will be removed and wait_for_idle expects the app to have units
    if cloud_name == "localhost":
        idle_apps = [DATA_INTEGRATOR]
    else:
        idle_apps = [DATA_INTEGRATOR, PGBOUNCER[cloud_name]]

    await ops_test.model.wait_for_idle(apps=idle_apps)
    await ops_test.model.add_relation(DATA_INTEGRATOR, PGBOUNCER[cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, PGBOUNCER[cloud_name]])

    logger.info("Relate and check the accessibility of the previously created database")
    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(
        f"Check assessibility of inserted data on {PGBOUNCER[cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        PGBOUNCER[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
