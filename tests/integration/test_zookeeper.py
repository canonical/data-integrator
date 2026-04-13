#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import logging
from pathlib import PosixPath

from jubilant_adapters import JujuFixture, gather

from .constants import APP, DATA_INTEGRATOR, DATABASE_NAME, ZOOKEEPER
from .helpers import (
    check_secrets_usage_matching_juju_version,
    fetch_action_database,
    fetch_action_get_credentials,
)

logger = logging.getLogger(__name__)


def test_deploy(juju: JujuFixture, app_charm: PosixPath, data_integrator_charm: PosixPath):
    gather(
        juju.ext.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        ),
        juju.ext.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"

    # config database name

    config = {"database-name": f"/{DATABASE_NAME}"}
    juju.ext.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"


def test_deploy_and_relate_zookeeper(juju: JujuFixture, cloud_name: str):
    """Test the relation with ZooKeeper and database accessibility."""
    provider_name = ZOOKEEPER[cloud_name]

    gather(
        juju.ext.model.deploy(
            provider_name,
            channel="3/edge",
            application_name=provider_name,
            num_units=1,
            series="jammy",
            trust=True,
        )
    )
    juju.ext.model.wait_for_idle(apps=[provider_name], wait_for_active=True)
    assert juju.ext.model.applications[provider_name].status == "active"
    integrator_relation = juju.ext.model.add_relation(DATA_INTEGRATOR, provider_name)

    with juju.ext.fast_forward(fast_interval="30s"):
        juju.ext.model.wait_for_idle(
            apps=[DATA_INTEGRATOR, provider_name], wait_for_active=True, idle_period=15
        )
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "active"

    # check if secrets are used on Juju3
    assert check_secrets_usage_matching_juju_version(
        juju,
        juju.ext.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )

    # get credential for ZooKeeper
    credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info(f"Create zNode on {ZOOKEEPER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "create-table",
        ZOOKEEPER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert zNode on {ZOOKEEPER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "insert-data",
        ZOOKEEPER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {ZOOKEEPER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        ZOOKEEPER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    #  remove relation and test connection again
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:zookeeper", f"{ZOOKEEPER[cloud_name]}:zookeeper"
    )

    juju.ext.model.wait_for_idle(apps=[ZOOKEEPER[cloud_name], DATA_INTEGRATOR])
    juju.ext.model.add_relation(DATA_INTEGRATOR, ZOOKEEPER[cloud_name])

    with juju.ext.fast_forward(fast_interval="30s"):
        juju.ext.model.wait_for_idle(
            apps=[DATA_INTEGRATOR, ZOOKEEPER[cloud_name]], wait_for_active=True, idle_period=15
        )

    # join with another relation and check the accessibility of the previously created database
    new_credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(
        f"Check assessibility of inserted data on {ZOOKEEPER[cloud_name]} with new credentials"
    )
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        ZOOKEEPER[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
