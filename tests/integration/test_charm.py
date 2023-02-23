#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import time
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from tests.integration.constants import (
    APP,
    DATA_INTEGRATOR,
    DATABASE_NAME,
    EXTRA_USER_ROLES,
    KAFKA,
    MONGODB,
    MYSQL,
    POSTGRESQL,
    TOPIC_NAME,
    ZOOKEEPER,
)
from tests.integration.helpers import (
    check_logs,
    fetch_action_database,
    fetch_action_get_credentials,
    fetch_action_kafka,
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


async def test_deploy_and_relate_postgresql(ops_test: OpsTest):
    """Test the relation with PostgreSQL and database accessibility."""
    await asyncio.gather(
        ops_test.model.deploy(
            POSTGRESQL[ops_test.cloud_name],
            channel="edge",
            application_name=POSTGRESQL[ops_test.cloud_name],
            num_units=1,
            series="focal",
            trust=True,
        )
    )
    await ops_test.model.wait_for_idle(
        apps=[POSTGRESQL[ops_test.cloud_name]],
        wait_for_active=True,
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
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name]])

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


@pytest.mark.skip
async def test_deploy_and_relate_mongodb(ops_test: OpsTest):
    """Test the relation with MongoDB and database accessibility."""
    channel = "dpe/edge" if ops_test.cloud_name == "localhost" else "edge"
    await asyncio.gather(
        ops_test.model.deploy(
            MONGODB[ops_test.cloud_name],
            channel=channel,
            application_name=MONGODB[ops_test.cloud_name],
            num_units=1,
            series="focal",
        )
    )
    await ops_test.model.wait_for_idle(apps=[MONGODB[ops_test.cloud_name]], wait_for_active=True)
    assert ops_test.model.applications[MONGODB[ops_test.cloud_name]].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, MONGODB[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB[ops_test.cloud_name]])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for MongoDB
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {MONGODB[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        MONGODB[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {MONGODB[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        MONGODB[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {MONGODB[ops_test.cloud_name]}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MONGODB[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    # drop relation and get new credential for the same collection
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB[ops_test.cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MONGODB[ops_test.cloud_name], DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, MONGODB[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB[ops_test.cloud_name]])

    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # test that different credentials are provided
    assert credentials != new_credentials

    logger.info(
        f"Check assessibility of inserted data on {MONGODB[ops_test.cloud_name]} with new credentials"
    )
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MONGODB[ops_test.cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB[ops_test.cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MONGODB[ops_test.cloud_name], DATA_INTEGRATOR])


async def test_deploy_and_relate_kafka(ops_test: OpsTest):
    """Test the relation with Kafka and the correct production and consumption of messagges."""
    await asyncio.gather(
        ops_test.model.deploy(
            ZOOKEEPER[ops_test.cloud_name],
            channel="edge",
            application_name=ZOOKEEPER[ops_test.cloud_name],
            num_units=1,
            series="jammy" if ops_test.cloud_name == "localhost" else "focal",
        ),
        ops_test.model.deploy(
            KAFKA[ops_test.cloud_name],
            channel="edge",
            application_name=KAFKA[ops_test.cloud_name],
            num_units=1,
            series="jammy",
        ),
    )

    await ops_test.model.wait_for_idle(apps=[ZOOKEEPER[ops_test.cloud_name]], timeout=1000)
    await ops_test.model.wait_for_idle(
        apps=[KAFKA[ops_test.cloud_name]], timeout=1000, status="waiting"
    )
    time.sleep(10)
    assert ops_test.model.applications[KAFKA[ops_test.cloud_name]].status == "waiting"
    assert ops_test.model.applications[ZOOKEEPER[ops_test.cloud_name]].status == "active"

    await ops_test.model.add_relation(KAFKA[ops_test.cloud_name], ZOOKEEPER[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(
        apps=[KAFKA[ops_test.cloud_name], ZOOKEEPER[ops_test.cloud_name]]
    )
    assert ops_test.model.applications[KAFKA[ops_test.cloud_name]].status == "active"
    assert ops_test.model.applications[ZOOKEEPER[ops_test.cloud_name]].status == "active"

    # configure topic and extra-user-roles
    config = {"topic-name": TOPIC_NAME, "extra-user-roles": EXTRA_USER_ROLES}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    await ops_test.model.wait_for_idle(apps=[KAFKA[ops_test.cloud_name], DATA_INTEGRATOR])
    await ops_test.model.add_relation(KAFKA[ops_test.cloud_name], DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(
        apps=[KAFKA[ops_test.cloud_name], ZOOKEEPER[ops_test.cloud_name], DATA_INTEGRATOR]
    )
    time.sleep(10)
    assert ops_test.model.applications[KAFKA[ops_test.cloud_name]].status == "active"
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"
    await ops_test.model.wait_for_idle(
        apps=[KAFKA[ops_test.cloud_name], ZOOKEEPER[ops_test.cloud_name], DATA_INTEGRATOR]
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
