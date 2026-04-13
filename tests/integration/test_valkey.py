#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from .constants import APP, DATA_INTEGRATOR, VALKEY, VALKEY_KEY_PREFIX
from .helpers import (
    fetch_action_database,
    fetch_action_get_credentials,
)
from .markers import only_with_juju_secrets

logger = logging.getLogger(__name__)


@only_with_juju_secrets
@pytest.mark.abort_on_fail
async def test_deploy(
    ops_test: OpsTest, app_charm: PosixPath, data_integrator_charm: PosixPath, cloud_name: str, valkey_charm: PosixPath
):
    """Deploys charms for testing."""
    model_config = {
        "logging-config": "<root>=INFO;unit=DEBUG",
    }
    await ops_test.model.set_config(model_config)

    await asyncio.gather(
        ops_test.model.deploy(
            valkey_charm,
            # channel="3.6/edge",
            application_name=VALKEY,
            num_units=3,
        ),
        ops_test.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        ),
        ops_test.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, VALKEY, APP],
        idle_period=10,
        timeout=1600,
    )


@only_with_juju_secrets
@pytest.mark.abort_on_fail
async def test_relate(ops_test: OpsTest, cloud_name: str):
    """Relates the charms."""
    logger.info("Set prefix config for Data Integrator")
    config = {"prefix-name": VALKEY_KEY_PREFIX}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    logger.info("Integrate with Valkey")
    await ops_test.model.add_relation(VALKEY, DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, VALKEY],
        status="active",
        idle_period=10,
        timeout=1600,
    )


@only_with_juju_secrets
@pytest.mark.abort_on_fail
async def test_read_write(ops_test: OpsTest, cloud_name: str):
    """Write and read to the key prefix."""
    logger.info("Getting credentials from Data Integrator")
    result = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    credentials = result[VALKEY]

    logger.info("Attempting to write data to Valkey")
    result = await fetch_action_database(
        unit=ops_test.model.applications[APP].units[0],
        action_name="insert-data",
        product=VALKEY,
        credentials=json.dumps(credentials),
        database_name=VALKEY_KEY_PREFIX,
    )
    assert result["ok"]

    logger.info("Attempting to read inserted data in Valkey")
    result = await fetch_action_database(
        unit=ops_test.model.applications[APP].units[0],
        action_name="check-inserted-data",
        product=VALKEY,
        credentials=json.dumps(credentials),
        database_name=VALKEY_KEY_PREFIX,
    )
    assert result["ok"]

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:valkey", f"{VALKEY}:valkey-client"
    )
    await ops_test.model.wait_for_idle(apps=[VALKEY, DATA_INTEGRATOR])

    await ops_test.model.add_relation(DATA_INTEGRATOR, VALKEY)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, VALKEY])

    result = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    new_credentials = result[VALKEY]

    # test that different credentials are provided
    assert credentials != new_credentials

    logger.info("Check accessibility of inserted data in Valkey with new credentials")
    result = await fetch_action_database(
        unit=ops_test.model.applications[APP].units[0],
        action_name="check-inserted-data",
        product=VALKEY,
        credentials=json.dumps(new_credentials),
        database_name=VALKEY_KEY_PREFIX,
    )
    assert result["ok"]
