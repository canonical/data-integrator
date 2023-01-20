#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import time
from subprocess import PIPE, check_output

import psycopg2
import pytest
from pymongo import MongoClient
from pytest_operator.plugin import OpsTest

from tests.integration.connector import MysqlConnector
from tests.integration.constants import (
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
    build_postgresql_connection_string,
    check_my_sql_data,
    create_table_mysql,
    fetch_action_get_credentials,
    insert_data_mysql,
    read_data_mysql,
)
from tests.integration.kafka_client import KafkaClient

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    data_integrator_charm = await ops_test.build_charm(".")
    await asyncio.gather(
        ops_test.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        )
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
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


@pytest.mark.skip  # skipping as we can't reconnect to same database (https://github.com/canonical/postgresql-k8s-operator/issues/64)
async def test_deploy_and_relate_postgresql(ops_test: OpsTest):
    """Test the relation with PostgreSQL and database accessibility."""
    await asyncio.gather(
        ops_test.model.deploy(
            "postgresql", channel="edge", application_name=POSTGRESQL, num_units=1, series="focal"
        )
    )
    await ops_test.model.wait_for_idle(apps=[POSTGRESQL])
    assert ops_test.model.applications[POSTGRESQL].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for PostgreSQL
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    # Build the complete connection string to connect to the database.
    connection_string = build_postgresql_connection_string(credentials)
    version = credentials[POSTGRESQL]["version"]

    # test connection for PostgreSQL with retrieved credentials
    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        # Check that it's possible to write and read data from the database that
        # was created for the application.
        connection.autocommit = True
        cursor.execute(f"DROP TABLE IF EXISTS {DATABASE_NAME};")
        cursor.execute(f"CREATE TABLE {DATABASE_NAME}(data TEXT);")
        cursor.execute(f"INSERT INTO {DATABASE_NAME}(data) VALUES('some data');")
        cursor.execute(f"SELECT data FROM {DATABASE_NAME};")
        data = cursor.fetchone()
        assert data[0] == "some data"

        # Check the version that the application received is the same on the database server.
        cursor.execute("SELECT version();")
        data = cursor.fetchone()[0].split(" ")[1]

        assert version == data

    #  remove relation and test connection again
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL}:database"
    )

    await ops_test.model.wait_for_idle(apps=[POSTGRESQL, DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL])

    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # Build the complete connection string to connect to the database.
    new_connection_string = build_postgresql_connection_string(new_credentials)
    # check that new credentials are provided
    assert new_connection_string != connection_string

    # Connect to the database using new credentials.
    with psycopg2.connect(new_connection_string) as connection, connection.cursor() as cursor:
        # Read data from previously created database.
        cursor.execute(f"SELECT data FROM {DATABASE_NAME};")
        data = cursor.fetchone()
        assert data[0] == "some data"


async def test_deploy_and_relate_mongodb(ops_test: OpsTest):
    """Test the relation with MongoDB and database accessibility."""
    await asyncio.gather(
        ops_test.model.deploy(
            "mongodb", channel="dpe/edge", application_name=MONGODB, num_units=1, series="focal"
        )
    )
    await ops_test.model.wait_for_idle(apps=[MONGODB])
    assert ops_test.model.applications[MONGODB].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, MONGODB)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for MongoDB
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    connection_string = credentials[MONGODB]["uris"]

    client = MongoClient(
        connection_string,
        directConnection=False,
        connect=False,
        serverSelectionTimeoutMS=1000,
        connectTimeoutMS=2000,
    )

    # test some operations
    db = client[DATABASE_NAME]
    test_collection = db["test_collection"]
    ubuntu = {"release_name": "Focal Fossa", "version": 20.04, "LTS": True}
    test_collection.insert_one(ubuntu)

    query = test_collection.find({}, {"release_name": 1})
    assert query[0]["release_name"] == "Focal Fossa"

    ubuntu_version = {"version": 20.04}
    ubuntu_name_updated = {"$set": {"release_name": "Fancy Fossa"}}
    test_collection.update_one(ubuntu_version, ubuntu_name_updated)

    query = test_collection.find({}, {"release_name": 1})
    assert query[0]["release_name"] == "Fancy Fossa"

    client.close()

    # drop relation and get new credential for the same collection
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MONGODB, DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, MONGODB)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB])

    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    new_connection_string = new_credentials[MONGODB]["uris"]

    # test that different credentials are provided
    assert connection_string != new_connection_string

    client = MongoClient(
        connection_string,
        directConnection=False,
        connect=False,
        serverSelectionTimeoutMS=1000,
        connectTimeoutMS=2000,
    )

    client = MongoClient(
        new_connection_string,
        directConnection=False,
        connect=False,
        serverSelectionTimeoutMS=1000,
        connectTimeoutMS=2000,
    )

    # test collection accessibility
    db = client[DATABASE_NAME]
    test_collection = db["test_collection"]
    query = test_collection.find({}, {"release_name": 1})
    assert query[0]["release_name"] == "Fancy Fossa"

    client.close()

    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB}:database"
    )

    await ops_test.model.wait_for_idle(apps=[MONGODB, DATA_INTEGRATOR])


@pytest.mark.abort_on_fail
async def test_deploy_and_relate_kafka(ops_test: OpsTest):
    """Test the relation with Kafka and the correct production and consumption of messagges."""
    await asyncio.gather(
        ops_test.model.deploy(
            ZOOKEEPER, channel="edge", application_name=ZOOKEEPER, num_units=1, series="focal"
        ),
        ops_test.model.deploy(
            KAFKA, channel="edge", application_name=KAFKA, num_units=1, series="jammy"
        ),
    )

    await ops_test.model.wait_for_idle(apps=[KAFKA, ZOOKEEPER])
    assert ops_test.model.applications[KAFKA].status == "waiting"
    assert ops_test.model.applications[ZOOKEEPER].status == "active"

    await ops_test.model.add_relation(KAFKA, ZOOKEEPER)
    await ops_test.model.wait_for_idle(apps=[KAFKA, ZOOKEEPER])
    assert ops_test.model.applications[KAFKA].status == "active"
    assert ops_test.model.applications[ZOOKEEPER].status == "active"

    #
    config = {"topic-name": TOPIC_NAME, "extra-user-roles": EXTRA_USER_ROLES}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    await ops_test.model.wait_for_idle(apps=[KAFKA, DATA_INTEGRATOR])
    await ops_test.model.add_relation(KAFKA, DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(apps=[KAFKA, ZOOKEEPER, DATA_INTEGRATOR])
    time.sleep(10)
    assert ops_test.model.applications[KAFKA].status == "active"
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"
    await ops_test.model.wait_for_idle(apps=[KAFKA, ZOOKEEPER, DATA_INTEGRATOR])

    # get credential for MYSQL
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # test connection for MYSQL with retrieved credentials
    # connection configuration

    username = credentials[KAFKA]["username"]
    password = credentials[KAFKA]["password"]
    servers = credentials[KAFKA]["endpoints"].split(",")
    security_protocol = "SASL_PLAINTEXT"

    if not (username and password and servers):
        raise KeyError("missing relation data from app charm")

    client = KafkaClient(
        servers=servers,
        username=username,
        password=password,
        topic=TOPIC_NAME,
        consumer_group_prefix=None,
        security_protocol=security_protocol,
    )

    client.create_topic()
    client.run_producer()

    logs = check_output(
        f"JUJU_MODEL={ops_test.model_full_name} juju ssh {KAFKA}/0 'find /var/snap/kafka/common/log-data'",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    ).splitlines()

    logger.debug(f"{logs=}")

    passed = False
    for log in logs:
        if TOPIC_NAME and "index" in log:
            passed = True
            break

    assert passed, "logs not found"
