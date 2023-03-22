#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import re
import time
from pathlib import PosixPath

import pytest
import requests
from pytest_operator.plugin import OpsTest

from tests.integration.constants import (  # OPENSEARCH_EXTRA_USER_ROLES,
    APP,
    DATA_INTEGRATOR,
    DATABASE_NAME,
    EXTRA_USER_ROLES,
    INDEX_NAME,
    KAFKA,
    MONGODB,
    MYSQL,
    OPENSEARCH,
    POSTGRESQL,
    TLS_CERTIFICATES_APP_NAME,
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
        # commented out while I'm not using it, reinstate before merge
        # ops_test.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])  # , APP])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"

    # config database name

    config = {"database-name": DATABASE_NAME}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"


@pytest.mark.skip
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


@pytest.mark.skip
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


@pytest.mark.skip
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


async def test_opensearch(ops_test: OpsTest):
    if ops_test.cloud_name != "localhost":
        pytest.skip("opensearch does not have a k8s charm yet.")

    def opensearch_request(credentials, method, endpoint, payload=None):
        """Send a request to the opensearch charm using the given credentials and parameters."""
        host = ops_test.model.applications[OPENSEARCH].units[0].public_address
        with requests.Session() as s:
            s.auth = (credentials.get("username"), credentials.get("password"))
            resp = s.request(
                verify=credentials.get("ca-chain"),
                method=method,
                url=f"https://{host}:9200/{endpoint}",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                **{"payload": payload} if payload else {},
            )
            resp.raise_for_status()
            return resp.json()

    # TODO change this to OPENSEARCH_EXTRA_USER_ROLES
    config = {"index-name": INDEX_NAME, "extra-user-roles": json.dumps({"roles": ["all_access"]})}
    tls_config = {"generate-self-signed-certificates": "true", "ca-common-name": "CN_CA"}
    # Set kernel params in model config opensearch can run
    model_config = {
        "logging-config": "<root>=INFO;unit=DEBUG",
        "update-status-hook-interval": "1m",
        "cloudinit-userdata": """postruncmd:
            - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
            - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
            - [ 'sysctl', '-w', 'vm.swappiness=0' ]
            - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
        """,
    }
    await ops_test.model.set_config(model_config)
    await asyncio.gather(
        ops_test.model.deploy(
            OPENSEARCH[ops_test.cloud_name],
            channel="edge",
            application_name=OPENSEARCH[ops_test.cloud_name],
            num_units=1,
        ),
        ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="edge", config=tls_config),
    )
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config),
    await asyncio.gather(
        ops_test.model.relate(OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME),
        ops_test.model.relate(DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name]),
    )
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME],
        status="active",
    )

    # get credentials for opensearch
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.error(credentials)

    bulk_payload = """{ "index" : { "_index": "albums", "_id" : "1" } }
{"artist": "Herbie Hancock", "genre": ["Jazz"],  "title": "Head Hunters"}
{ "index" : { "_index": "albums", "_id" : "2" } }
{"artist": "Lydian Collective", "genre": ["Jazz"],  "title": "Adventure"}
{ "index" : { "_index": "albums", "_id" : "3" } }
{"artist": "Liquid Tension Experiment", "genre": ["Prog", "Metal"],  "title": "Liquid Tension Experiment 2"}
"""
    opensearch_request(credentials, "GET", endpoint="")
    opensearch_request(credentials, "POST", endpoint="/_bulk", payload=re.escape(bulk_payload))
    get_jazz = opensearch_request(credentials, "GET", endpoint="/albums/_search?q=Jazz")
    artists = [
        hit.get("_source", {}).get("artist") for hit in get_jazz.get("hits", {}).get("hits", [{}])
    ]
    assert set(artists) == {"Herbie Hancock", "Lydian Collective"}

    await ops_test.model.applications[OPENSEARCH[ops_test.cloud_name]].remove_relation(
        OPENSEARCH[ops_test.cloud_name], DATA_INTEGRATOR
    )
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME],
            status="active",
        )

    await asyncio.gather(
        ops_test.model.relate(OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME),
        ops_test.model.relate(DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name]),
    )
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME],
            status="active",
        )

    # get new credentials for opensearch
    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.error(new_credentials)

    get_jazz_again = opensearch_request(new_credentials, "GET", endpoint="/albums/_search?q=Jazz")
    artists = [
        hit.get("_source", {}).get("artist")
        for hit in get_jazz_again.get("hits", {}).get("hits", [{}])
    ]
    assert set(artists) == {"Herbie Hancock", "Lydian Collective"}

    # Old credentials should have been revoked.
    with pytest.raises(requests.HTTPError):
        opensearch_request(credentials, "GET", endpoint="")
