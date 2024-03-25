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
    EXTRA_USER_ROLES,
    KAFKA,
    TOPIC_NAME,
    ZOOKEEPER,
)
from .helpers import check_logs, fetch_action_get_credentials, fetch_action_kafka

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

    config = {"topic-name": TOPIC_NAME, "extra-user-roles": EXTRA_USER_ROLES}
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
async def test_deploy_and_relate_kafka(ops_test: OpsTest):
    """Test the relation with Kafka and the correct production and consumption of messagges."""
    await asyncio.gather(
        ops_test.model.deploy(
            ZOOKEEPER[ops_test.cloud_name],
            channel="edge",
            application_name=ZOOKEEPER[ops_test.cloud_name],
            num_units=1,
            series="jammy",
        ),
        ops_test.model.deploy(
            KAFKA[ops_test.cloud_name],
            channel="edge",
            application_name=KAFKA[ops_test.cloud_name],
            num_units=1,
            series="jammy",
        ),
    )

    await ops_test.model.wait_for_idle(
        apps=[ZOOKEEPER[ops_test.cloud_name]], timeout=1000, status="active"
    )
    await ops_test.model.wait_for_idle(
        apps=[KAFKA[ops_test.cloud_name]], timeout=1000, status="blocked"
    )

    await ops_test.model.add_relation(KAFKA[ops_test.cloud_name], ZOOKEEPER[ops_test.cloud_name])
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[KAFKA[ops_test.cloud_name], ZOOKEEPER[ops_test.cloud_name]],
            timeout=2000,
            idle_period=60,
            status="active",
        )

    await ops_test.model.add_relation(KAFKA[ops_test.cloud_name], DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(
        apps=[KAFKA[ops_test.cloud_name], ZOOKEEPER[ops_test.cloud_name], DATA_INTEGRATOR],
        timeout=2000,
        idle_period=60,
        status="active",
    )

    # get credential for Kafka
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info("Create topic")
    await fetch_action_kafka(
        ops_test.model.applications[APP].units[0],
        "create-topic",
        KAFKA[ops_test.cloud_name],
        json.dumps(credentials),
        TOPIC_NAME,
    )

    logger.info("Produce messages")
    await fetch_action_kafka(
        ops_test.model.applications[APP].units[0],
        "produce-messages",
        KAFKA[ops_test.cloud_name],
        json.dumps(credentials),
        TOPIC_NAME,
    )
    logger.info("Check messages in logs")
    check_logs(
        model_full_name=ops_test.model_full_name,
        kafka_unit_name=f"{KAFKA[ops_test.cloud_name]}/0",
        topic=TOPIC_NAME,
    )

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:kafka", f"{KAFKA[ops_test.cloud_name]}:kafka-client"
    )
    await ops_test.model.wait_for_idle(apps=[KAFKA[ops_test.cloud_name], DATA_INTEGRATOR])

    await ops_test.model.add_relation(DATA_INTEGRATOR, KAFKA[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, KAFKA[ops_test.cloud_name]])

    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # test that different credentials are provided
    assert credentials != new_credentials
    logger.info("Produce messages")
    await fetch_action_kafka(
        ops_test.model.applications[APP].units[0],
        "produce-messages",
        KAFKA[ops_test.cloud_name],
        json.dumps(new_credentials),
        TOPIC_NAME,
    )
    logger.info("Check messages in logs")
    check_logs(
        model_full_name=ops_test.model_full_name,
        kafka_unit_name=f"{KAFKA[ops_test.cloud_name]}/0",
        topic=TOPIC_NAME,
    )


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_topic_setting(ops_test: OpsTest):
    """Tests that requesting a wildcard topic will generate an error."""
    # TODO Fix timing issues with recovery from error
    config = {"topic-name": "*"}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR],
        raise_on_error=False,
        idle_period=40,
    )
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "error"
