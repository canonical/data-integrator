#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging

# import time
from pathlib import PosixPath

import pytest

# from pymongo import MongoClient
from pytest_operator.plugin import OpsTest

from tests.integration.connector import MysqlConnector
from tests.integration.constants import (  # EXTRA_USER_ROLES,; KAFKA,; MONGODB,; TOPIC_NAME,; ZOOKEEPER,
    DATA_INTEGRATOR,
    DATABASE_NAME,
    MONGODB,
    MYSQL,
    POSTGRESQL,
)
from tests.integration.helpers import (
    check_my_sql_data,
    create_table_mysql,
    fetch_action_database,
    fetch_action_get_credentials,
    insert_data_mysql,
    read_data_mysql,
)

# from tests.integration.kafka_client import KafkaClient

# from subprocess import PIPE, check_output


logger = logging.getLogger(__name__)

APP = "app"


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


@pytest.mark.skip  # skipping as we can't deploy MYSQL (https://github.com/canonical/mysql-operator/pull/73)
async def test_deploy_and_relate_mysql(ops_test: OpsTest):
    """Test the relation with MySQL and database accessibility."""
    await asyncio.gather(
        ops_test.model.deploy(
            "mysql", channel="edge", application_name=MYSQL, num_units=1, series="focal"
        )
    )
    await ops_test.model.wait_for_idle(apps=[MYSQL])
    assert ops_test.model.applications[MYSQL].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, MYSQL)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for MYSQL
    credentials = fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # test connection for MYSQL with retrieved credentials
    # connection configuration
    config = {
        "user": credentials[MYSQL]["username"],
        "password": credentials[MYSQL]["password"],
        "host": credentials[MYSQL]["endpoints"].split(":")[0],
        "database": DATABASE_NAME,
        "raise_on_warnings": False,
    }

    with MysqlConnector(config) as cursor:

        create_table_mysql(cursor, DATABASE_NAME)

        insert_data_mysql(
            cursor,
            DATABASE_NAME,
            credentials[MYSQL]["username"],
            credentials[MYSQL]["password"],
            credentials[MYSQL]["endpoints"],
            credentials[MYSQL]["version"],
            credentials[MYSQL]["read-only-endpoints"],
        )

    with MysqlConnector(config) as cursor:

        rows = read_data_mysql(cursor, credentials[MYSQL]["username"])
        # check that values are written in the table
        check_my_sql_data(rows, credentials)

    #  remove relation and test connection again
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{MYSQL}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MYSQL, DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, MYSQL)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL])

    # join with another relation and check the accessibility of the previously created database
    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    new_config = {
        "user": new_credentials[MYSQL]["username"],
        "password": new_credentials[MYSQL]["password"],
        "host": new_credentials[MYSQL]["endpoints"].split(":")[0],
        "database": DATABASE_NAME,
        "raise_on_warnings": False,
    }
    # test connection with new credentials and check the previously committed data are present.
    with MysqlConnector(new_config) as cursor:
        rows = read_data_mysql(cursor, credentials[MYSQL]["username"])
        # check that values are written in the table
        check_my_sql_data(rows, credentials)


@pytest.mark.skip
async def test_deploy_and_relate_postgresql(ops_test: OpsTest):
    """Test the relation with PostgreSQL and database accessibility."""
    await asyncio.gather(
        ops_test.model.deploy(
            "postgresql",
            channel="edge",
            application_name=POSTGRESQL[ops_test.cloud_name],
            num_units=1,
            series="focal",
        )
    )
    await ops_test.model.wait_for_idle(apps=[POSTGRESQL[ops_test.cloud_name]])
    assert ops_test.model.applications[POSTGRESQL[ops_test.cloud_name]].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name]])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for PostgreSQL
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        POSTGRESQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )

    await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        POSTGRESQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )

    await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        POSTGRESQL[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL[ops_test.cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[POSTGRESQL[ops_test.cloud_name], DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL[ops_test.cloud_name]])

    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    # check that new credentials are provided
    assert credentials != new_credentials

    await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        POSTGRESQL[ops_test.cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )


async def test_deploy_and_relate_mongodb(ops_test: OpsTest):
    """Test the relation with MongoDB and database accessibility."""
    channel = "dpe/edge" if ops_test.cloud_name == "localhost" else "edge"
    await asyncio.gather(
        ops_test.model.deploy(
            "mongodb",
            channel=channel,
            application_name=MONGODB[ops_test.cloud_name],
            num_units=1,
            series="focal",
        )
    )
    await ops_test.model.wait_for_idle(apps=[MONGODB[ops_test.cloud_name]])
    assert ops_test.model.applications[MONGODB[ops_test.cloud_name]].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, MONGODB[ops_test.cloud_name])
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB[ops_test.cloud_name]])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for MongoDB
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        MONGODB[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )

    await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        MONGODB[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )

    await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MONGODB[ops_test.cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )

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

    await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        MONGODB[ops_test.cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB[ops_test.cloud_name]}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MONGODB[ops_test.cloud_name], DATA_INTEGRATOR])


# @pytest.mark.skip
# @pytest.mark.abort_on_fail
# async def test_deploy_and_relate_kafka(ops_test: OpsTest):
#     """Test the relation with Kafka and the correct production and consumption of messagges."""
#     await asyncio.gather(
#         ops_test.model.deploy(
#             ZOOKEEPER, channel="edge", application_name=ZOOKEEPER, num_units=1, series="jammy"
#         ),
#         ops_test.model.deploy(
#             KAFKA, channel="edge", application_name=KAFKA, num_units=1, series="jammy"
#         ),
#     )

#     await ops_test.model.wait_for_idle(apps=[KAFKA, ZOOKEEPER])
#     assert ops_test.model.applications[KAFKA].status == "waiting"
#     assert ops_test.model.applications[ZOOKEEPER].status == "active"

#     await ops_test.model.add_relation(KAFKA, ZOOKEEPER)
#     await ops_test.model.wait_for_idle(apps=[KAFKA, ZOOKEEPER])
#     assert ops_test.model.applications[KAFKA].status == "active"
#     assert ops_test.model.applications[ZOOKEEPER].status == "active"

#     #
#     config = {"topic-name": TOPIC_NAME, "extra-user-roles": EXTRA_USER_ROLES}
#     await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

#     # test the active/waiting status for relation
#     await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
#     await ops_test.model.wait_for_idle(apps=[KAFKA, DATA_INTEGRATOR])
#     await ops_test.model.add_relation(KAFKA, DATA_INTEGRATOR)
#     await ops_test.model.wait_for_idle(apps=[KAFKA, ZOOKEEPER, DATA_INTEGRATOR])
#     time.sleep(10)
#     assert ops_test.model.applications[KAFKA].status == "active"
#     assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"
#     await ops_test.model.wait_for_idle(apps=[KAFKA, ZOOKEEPER, DATA_INTEGRATOR])

#     # get credential for MYSQL
#     credentials = await fetch_action_get_credentials(
#         ops_test.model.applications[DATA_INTEGRATOR].units[0]
#     )

#     # test connection for MYSQL with retrieved credentials
#     # connection configuration

#     username = credentials[KAFKA]["username"]
#     password = credentials[KAFKA]["password"]
#     servers = credentials[KAFKA]["endpoints"].split(",")
#     security_protocol = "SASL_PLAINTEXT"

#     if not (username and password and servers):
#         raise KeyError("missing relation data from app charm")

#     client = KafkaClient(
#         servers=servers,
#         username=username,
#         password=password,
#         topic=TOPIC_NAME,
#         consumer_group_prefix=None,
#         security_protocol=security_protocol,
#     )

#     client.create_topic()
#     client.run_producer()

#     logs = check_output(
#         f"JUJU_MODEL={ops_test.model_full_name} juju ssh
# {KAFKA}/0 'find /var/snap/kafka/common/log-data'",
#         stderr=PIPE,
#         shell=True,
#         universal_newlines=True,
#     ).splitlines()

#     logger.debug(f"{logs=}")

#     passed = False
#     for log in logs:
#         if TOPIC_NAME and "index" in log:
#             passed = True
#             break

#     assert passed, "logs not found"
