#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest
from spark_test.core.s3 import Bucket, Credentials
from spark_test.fixtures.s3 import bucket  # noqa

from .constants import APP, DATA_INTEGRATOR, DATABASE_NAME
from .helpers import (
    check_secrets_usage_matching_juju_version,
    fetch_action_database,
    fetch_action_get_credentials,
)
from .markers import only_on_microk8s, only_with_juju_3

logger = logging.getLogger(__name__)


KYUUBI = "kyuubi"
KYUUBI_APP_NAME = "kyuubi-k8s"
S3_APP_NAME = "s3-integrator"
INTEGRATION_HUB_APP_NAME = "spark-integration-hub-k8s"
POSTGRESQL_APP_NAME = "postgresql-k8s"


@only_on_microk8s
@only_with_juju_3
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_deploy_data_integrator(
    ops_test: OpsTest, app_charm: PosixPath, data_integrator_charm: PosixPath, cloud_name: str
):
    await asyncio.gather(
        ops_test.model.deploy(
            data_integrator_charm,
            application_name="data-integrator",
            num_units=1,
            series="jammy",
        ),
        ops_test.model.deploy(
            app_charm,
            application_name=APP,
            num_units=1,
            series="jammy",
        ),
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"

    # config database name

    config = {"database-name": f"/{DATABASE_NAME}"}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"


@only_on_microk8s
@only_with_juju_3
@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_deploy_kyuubi_setup(
    ops_test: OpsTest,
    credentials: Credentials,
    bucket: Bucket,  # noqa: F811
    cloud_name: str,  # noqa: F811
):
    kyuubi_deploy_args = {
        "application_name": KYUUBI_APP_NAME,
        "num_units": 1,
        "channel": "latest/edge",
        "series": "jammy",
        "trust": True,
    }

    # Deploy the Kyuubi charm and wait
    logger.info("Deploying kyuubi-k8s charm...")
    await ops_test.model.deploy(KYUUBI_APP_NAME, **kyuubi_deploy_args)
    logger.info("Waiting for kyuubi-k8s app to be settle...")
    await ops_test.model.wait_for_idle(apps=[KYUUBI_APP_NAME], status="blocked")
    logger.info(f"State of kyuubi-k8s app: {ops_test.model.applications[KYUUBI_APP_NAME].status}")

    # Set Kyuubi config options and wait
    logger.info("Setting configuration for kyuubi-k8s charm...")
    namespace = ops_test.model.name
    username = "kyuubi-spark-engine"
    await ops_test.model.applications[KYUUBI_APP_NAME].set_config({
        "namespace": namespace,
        "service-account": username,
    })
    logger.info("Waiting for kyuubi-k8s app to settle...")
    await ops_test.model.wait_for_idle(apps=[KYUUBI_APP_NAME], status="blocked", idle_period=20)

    # Deploy the S3 Integrator charm and wait
    s3_deploy_args = {"application_name": S3_APP_NAME, "channel": "edge", "series": "jammy"}
    logger.info("Deploying s3-integrator charm...")
    await ops_test.model.deploy(S3_APP_NAME, **s3_deploy_args)
    logger.info("Waiting for s3-integrator app to be idle...")
    await ops_test.model.wait_for_idle(apps=[S3_APP_NAME])

    # Receive S3 params from fixture, apply them and wait
    endpoint_url = bucket.s3.meta.endpoint_url
    access_key = credentials.access_key
    secret_key = credentials.secret_key
    bucket_name = bucket.bucket_name
    path = "spark-events/"

    logger.info("Setting up s3 credentials in s3-integrator charm")
    s3_integrator_unit = ops_test.model.applications[S3_APP_NAME].units[0]
    action = await s3_integrator_unit.run_action(
        action_name="sync-s3-credentials", **{"access-key": access_key, "secret-key": secret_key}
    )
    await action.wait()
    logger.info("Setting configuration for s3-integrator charm...")
    await ops_test.model.applications[S3_APP_NAME].set_config({
        "bucket": bucket_name,
        "path": path,
        "endpoint": endpoint_url,
    })
    logger.info("Waiting for s3-integrator app to be idle and active...")
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[S3_APP_NAME], status="active")

    # Deploy the integration hub charm and wait
    hub_deploy_args = {
        "application_name": INTEGRATION_HUB_APP_NAME,
        "channel": "latest/edge",
        "series": "jammy",
        "trust": True,
    }
    logger.info("Deploying integration-hub charm...")
    await ops_test.model.deploy(INTEGRATION_HUB_APP_NAME, **hub_deploy_args)
    logger.info("Waiting for integration_hub and s3-integrator app to be idle and active...")
    await ops_test.model.wait_for_idle(
        apps=[INTEGRATION_HUB_APP_NAME, S3_APP_NAME],
        status="active",
    )

    # Integrate integration hub with S3 integrator and wait
    logger.info("Integrating integration-hub charm with s3-integrator charm...")
    await ops_test.model.add_relation(S3_APP_NAME, INTEGRATION_HUB_APP_NAME)
    logger.info("Waiting for s3-integrator and integration-hub charms to be idle and active...")
    await ops_test.model.wait_for_idle(
        apps=[
            INTEGRATION_HUB_APP_NAME,
            S3_APP_NAME,
        ],
        status="active",
    )

    # Add configuration key to prevent resource starvation during tests
    unit = ops_test.model.applications[INTEGRATION_HUB_APP_NAME].units[0]
    action = await unit.run_action(
        action_name="add-config", conf="spark.kubernetes.executor.request.cores=0.1"
    )
    _ = await action.wait()

    # Integrate Kyuubi with Integration Hub and wait
    logger.info("Integrating kyuubi charm with integration-hub charm...")
    await ops_test.model.add_relation(INTEGRATION_HUB_APP_NAME, KYUUBI_APP_NAME)
    logger.info(
        "Waiting for kyuubi, s3-integrator and integration_hub charms to be idle and active..."
    )

    # Wait for everything to settle down
    await ops_test.model.wait_for_idle(
        apps=[
            KYUUBI_APP_NAME,
            INTEGRATION_HUB_APP_NAME,
            S3_APP_NAME,
        ],
        idle_period=20,
        status="active",
    )

    # Deploy the postgresql charm and wait
    hub_deploy_args = {
        "application_name": POSTGRESQL_APP_NAME,
        "channel": "16/stable",
        "series": "noble",
        "trust": True,
    }
    logger.info("Deploying postgresql charm...")
    await ops_test.model.deploy(POSTGRESQL_APP_NAME, **hub_deploy_args)
    logger.info("Waiting for postgresql charm to be idle and active...")
    await ops_test.model.wait_for_idle(
        apps=[POSTGRESQL_APP_NAME],
        status="active",
    )

    # Integrate Kyuubi with Postgresql and wait
    logger.info("Integrating kyuubi charm with postgresql charm...")
    await ops_test.model.add_relation(f"{KYUUBI_APP_NAME}:auth-db", POSTGRESQL_APP_NAME)
    logger.info(
        "Waiting for kyuubi, s3-integrator and integration_hub, and postgresql charms to be idle and active..."
    )

    # Wait for everything to settle down
    await ops_test.model.wait_for_idle(
        apps=[
            KYUUBI_APP_NAME,
            INTEGRATION_HUB_APP_NAME,
            S3_APP_NAME,
            POSTGRESQL_APP_NAME,
        ],
        idle_period=20,
        status="active",
    )
    logger.info("Successfully deployed minimal working Kyuubi setup.")


@only_on_microk8s
@only_with_juju_3
@pytest.mark.group(1)
async def test_relate_kyuubi_with_data_integrator(ops_test: OpsTest, cloud_name: str):
    """Test the relation with ZooKeeper and database accessibility."""
    integrator_relation = await ops_test.model.add_relation(DATA_INTEGRATOR, KYUUBI_APP_NAME)

    async with ops_test.fast_forward(fast_interval="30s"):
        await ops_test.model.wait_for_idle(
            apps=[DATA_INTEGRATOR, KYUUBI_APP_NAME], wait_for_active=True, idle_period=15
        )
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"
    assert ops_test.model.applications[KYUUBI_APP_NAME].status == "active"

    # check if secrets are used on Juju3
    assert await check_secrets_usage_matching_juju_version(
        ops_test,
        ops_test.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )


@only_with_juju_3
@only_on_microk8s
@pytest.mark.group(1)
async def test_data_read_write_on_kyuubi(ops_test: OpsTest, cloud_name: str):
    """Test the relation with ZooKeeper and database accessibility."""
    # get credential for Kyuubi
    kyuubi_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    ### INSERT DATA

    logger.info(f"Create table on {KYUUBI}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "create-table",
        KYUUBI,
        json.dumps(kyuubi_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info(f"Insert rows to table on {KYUUBI}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "insert-data",
        KYUUBI,
        json.dumps(kyuubi_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info(f"Check assessibility of inserted data on {KYUUBI}")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        KYUUBI,
        json.dumps(kyuubi_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    #  remove relation and test connection again
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:kyuubi", f"{KYUUBI_APP_NAME}:jdbc"
    )

    await ops_test.model.wait_for_idle(apps=[KYUUBI_APP_NAME, DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, KYUUBI_APP_NAME)

    async with ops_test.fast_forward(fast_interval="30s"):
        await ops_test.model.wait_for_idle(
            apps=[DATA_INTEGRATOR, KYUUBI_APP_NAME], wait_for_active=True, idle_period=15
        )

    # Check the accessibility of the previously created database
    new_kyuubi_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert kyuubi_credentials != new_kyuubi_credentials

    logger.info(f"Check assessibility of inserted data on {KYUUBI} with new credentials")
    result = await fetch_action_database(
        ops_test.model.applications[APP].units[0],
        "check-inserted-data",
        KYUUBI,
        json.dumps(new_kyuubi_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
