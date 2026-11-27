#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from .constants import DATA_INTEGRATOR, KAFKA, KARAPACE, SUBJECT_NAME
from .helpers import check_karapace_api, fetch_action_get_credentials

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest, data_integrator_charm: PosixPath):
    await ops_test.model.deploy(
        data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR], idle_period=30)
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"

    config = {"subject-name": SUBJECT_NAME}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/blocked status for relation
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR],
        raise_on_error=False,
        status="blocked",
        idle_period=60,
    )
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"


@pytest.mark.abort_on_fail
async def test_deploy_and_relate_karapace(ops_test: OpsTest, cloud_name: str):
    """Test the relation with Karapace."""
    await asyncio.gather(
        ops_test.model.deploy(
            KARAPACE[cloud_name],
            channel="latest/stable",
            application_name=KARAPACE[cloud_name],
            num_units=1,
            series="noble",
        ),
        ops_test.model.deploy(
            KAFKA[cloud_name],
            channel="4/stable",
            application_name=KAFKA[cloud_name],
            num_units=1,
            series="noble",
            config={"roles": "broker,controller"},
        ),
    )

    await ops_test.model.add_relation(KAFKA[cloud_name], KARAPACE[cloud_name])
    async with ops_test.fast_forward(fast_interval="60s"):
        await ops_test.model.wait_for_idle(
            apps=[KAFKA[cloud_name], KARAPACE[cloud_name]],
            timeout=2000,
            idle_period=30,
            status="active",
        )

    await ops_test.model.add_relation(KARAPACE[cloud_name], DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(
        apps=[KAFKA[cloud_name], KARAPACE[cloud_name], DATA_INTEGRATOR],
        timeout=2000,
        idle_period=30,
        status="active",
    )


async def test_credentials(ops_test: OpsTest, cloud_name: str):
    """Test get-credentials action and proper credentials rotation."""
    # get credential for Karapace
    results = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info("Checking Karapace API is accessible using credentials...")
    assert check_karapace_api(results=results)

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:karapace", f"{KARAPACE[cloud_name]}"
    )
    await ops_test.model.wait_for_idle(apps=[KARAPACE[cloud_name], DATA_INTEGRATOR])

    await ops_test.model.add_relation(DATA_INTEGRATOR, KARAPACE[cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, KARAPACE[cloud_name]])

    new_results = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # test that different credentials are provided
    for key in ("username", "password"):
        assert results["karapace"][key] != new_results["karapace"][key]

    logger.info("Checking Karapace API is accessible using new credentials...")
    assert check_karapace_api(results=new_results)
