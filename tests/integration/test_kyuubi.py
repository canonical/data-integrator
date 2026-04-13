#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import logging
from pathlib import PosixPath

from jubilant_adapters import JujuFixture, gather
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
def test_deploy_data_integrator(
    juju: JujuFixture, app_charm: PosixPath, data_integrator_charm: PosixPath, cloud_name: str
):
    gather(
        juju.ext.model.deploy(
            data_integrator_charm,
            application_name="data-integrator",
            num_units=1,
            series="jammy",
        ),
        juju.ext.model.deploy(
            app_charm,
            application_name=APP,
            num_units=1,
            series="jammy",
        ),
    )
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"

    # config database name

    config = {"database-name": f"/{DATABASE_NAME}"}
    juju.ext.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"


@only_on_microk8s
@only_with_juju_3
def test_deploy_kyuubi_setup(
    juju: JujuFixture,
    credentials: Credentials,
    bucket: Bucket,  # noqa: F811
    cloud_name: str,  # noqa: F811
):
    kyuubi_deploy_args = {
        "application_name": KYUUBI_APP_NAME,
        "num_units": 1,
        "channel": "3.5/edge",
        "series": "jammy",
        "trust": True,
    }

    # Deploy the Kyuubi charm and wait
    logger.info("Deploying kyuubi-k8s charm...")
    juju.ext.model.deploy(KYUUBI_APP_NAME, **kyuubi_deploy_args)
    logger.info("Waiting for kyuubi-k8s app to be settle...")
    juju.ext.model.wait_for_idle(apps=[KYUUBI_APP_NAME], status="blocked")
    logger.info(f"State of kyuubi-k8s app: {juju.ext.model.applications[KYUUBI_APP_NAME].status}")

    # Set Kyuubi config options and wait
    logger.info("Setting configuration for kyuubi-k8s charm...")
    namespace = juju.ext.model.name
    username = "kyuubi-spark-engine"
    juju.ext.model.applications[KYUUBI_APP_NAME].set_config({
        "namespace": namespace,
        "service-account": username,
    })
    logger.info("Waiting for kyuubi-k8s app to settle...")
    juju.ext.model.wait_for_idle(apps=[KYUUBI_APP_NAME], status="blocked", idle_period=20)

    # Deploy the S3 Integrator charm and wait
    s3_deploy_args = {"application_name": S3_APP_NAME, "channel": "edge", "series": "jammy"}
    logger.info("Deploying s3-integrator charm...")
    juju.ext.model.deploy(S3_APP_NAME, **s3_deploy_args)
    logger.info("Waiting for s3-integrator app to be idle...")
    juju.ext.model.wait_for_idle(apps=[S3_APP_NAME])

    # Receive S3 params from fixture, apply them and wait
    endpoint_url = bucket.s3.meta.endpoint_url
    access_key = credentials.access_key
    secret_key = credentials.secret_key
    bucket_name = bucket.bucket_name
    path = "spark-events/"

    logger.info("Setting up s3 credentials in s3-integrator charm")
    s3_integrator_unit = juju.ext.model.applications[S3_APP_NAME].units[0]
    action = s3_integrator_unit.run_action(
        action_name="sync-s3-credentials", **{"access-key": access_key, "secret-key": secret_key}
    )
    action.wait()
    logger.info("Setting configuration for s3-integrator charm...")
    juju.ext.model.applications[S3_APP_NAME].set_config({
        "bucket": bucket_name,
        "path": path,
        "endpoint": endpoint_url,
    })
    logger.info("Waiting for s3-integrator app to be idle and active...")
    with juju.ext.fast_forward():
        juju.ext.model.wait_for_idle(apps=[S3_APP_NAME], status="active")

    # Deploy the integration hub charm and wait
    hub_deploy_args = {
        "application_name": INTEGRATION_HUB_APP_NAME,
        "channel": "3/edge",
        "series": "jammy",
        "trust": True,
    }
    logger.info("Deploying integration-hub charm...")
    juju.ext.model.deploy(INTEGRATION_HUB_APP_NAME, **hub_deploy_args)
    logger.info("Waiting for integration_hub and s3-integrator app to be idle and active...")
    juju.ext.model.wait_for_idle(
        apps=[INTEGRATION_HUB_APP_NAME, S3_APP_NAME],
        status="active",
    )

    # Integrate integration hub with S3 integrator and wait
    logger.info("Integrating integration-hub charm with s3-integrator charm...")
    juju.ext.model.add_relation(S3_APP_NAME, INTEGRATION_HUB_APP_NAME)
    logger.info("Waiting for s3-integrator and integration-hub charms to be idle and active...")
    juju.ext.model.wait_for_idle(
        apps=[
            INTEGRATION_HUB_APP_NAME,
            S3_APP_NAME,
        ],
        status="active",
    )

    # Integrate Kyuubi with Integration Hub and wait
    logger.info("Integrating kyuubi charm with integration-hub charm...")
    juju.ext.model.add_relation(INTEGRATION_HUB_APP_NAME, KYUUBI_APP_NAME)
    logger.info(
        "Waiting for kyuubi, s3-integrator and integration_hub charms to be idle and active..."
    )

    # Deploy the postgresql charm and wait
    hub_deploy_args = {
        "application_name": POSTGRESQL_APP_NAME,
        "channel": "14/stable",
        "series": "jammy",
        "trust": True,
    }
    logger.info("Deploying postgresql charm...")
    juju.ext.model.deploy(POSTGRESQL_APP_NAME, **hub_deploy_args)

    # Integrate Kyuubi with Postgresql and wait
    logger.info("Integrating kyuubi charm with postgresql charm...")
    juju.ext.model.add_relation(f"{KYUUBI_APP_NAME}:auth-db", POSTGRESQL_APP_NAME)
    logger.info(
        "Waiting for kyuubi, s3-integrator and integration_hub, and postgresql charms to be idle and active..."
    )

    # Wait for everything to settle down
    juju.ext.model.wait_for_idle(
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
def test_relate_kyuubi_with_data_integrator(juju: JujuFixture, cloud_name: str):
    """Test the relation with ZooKeeper and database accessibility."""
    integrator_relation = juju.ext.model.add_relation(DATA_INTEGRATOR, KYUUBI_APP_NAME)

    with juju.ext.fast_forward(fast_interval="30s"):
        juju.ext.model.wait_for_idle(
            apps=[DATA_INTEGRATOR, KYUUBI_APP_NAME], wait_for_active=True, idle_period=15
        )
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "active"
    assert juju.ext.model.applications[KYUUBI_APP_NAME].status == "active"

    # check if secrets are used on Juju3
    assert check_secrets_usage_matching_juju_version(
        juju,
        juju.ext.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )


@only_with_juju_3
@only_on_microk8s
def test_data_read_write_on_kyuubi(juju: JujuFixture, cloud_name: str):
    """Test the relation with ZooKeeper and database accessibility."""
    # get credential for Kyuubi
    kyuubi_credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    ### INSERT DATA

    logger.info(f"Create table on {KYUUBI}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "create-table",
        KYUUBI,
        json.dumps(kyuubi_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info(f"Insert rows to table on {KYUUBI}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "insert-data",
        KYUUBI,
        json.dumps(kyuubi_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info(f"Check assessibility of inserted data on {KYUUBI}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        KYUUBI,
        json.dumps(kyuubi_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    #  remove relation and test connection again
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:kyuubi", f"{KYUUBI_APP_NAME}:jdbc"
    )

    juju.ext.model.wait_for_idle(apps=[KYUUBI_APP_NAME, DATA_INTEGRATOR])
    juju.ext.model.add_relation(DATA_INTEGRATOR, KYUUBI_APP_NAME)

    with juju.ext.fast_forward(fast_interval="30s"):
        juju.ext.model.wait_for_idle(
            apps=[DATA_INTEGRATOR, KYUUBI_APP_NAME], wait_for_active=True, idle_period=15
        )

    # Check the accessibility of the previously created database
    new_kyuubi_credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert kyuubi_credentials != new_kyuubi_credentials

    logger.info(f"Check assessibility of inserted data on {KYUUBI} with new credentials")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        KYUUBI,
        json.dumps(new_kyuubi_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
