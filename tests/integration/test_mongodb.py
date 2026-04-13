#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import logging
from pathlib import PosixPath

from jubilant_adapters import JujuFixture, gather

from .constants import APP, DATA_INTEGRATOR, DATABASE_NAME, MONGODB
from .helpers import (
    check_secrets_usage_matching_juju_version,
    fetch_action_database,
    fetch_action_get_credentials,
)
from .markers import only_with_juju_secrets

logger = logging.getLogger(__name__)


@only_with_juju_secrets
def test_deploy(
    juju: JujuFixture,
    app_charm: PosixPath,
    data_integrator_charm: PosixPath,
    cloud_name: str,
):
    gather(
        juju.ext.model.deploy(
            data_integrator_charm,
            application_name="data-integrator",
            num_units=1,
            series="jammy",
        ),
        juju.ext.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"

    # config database name

    config = {"database-name": DATABASE_NAME}
    juju.ext.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"


@only_with_juju_secrets
def test_deploy_and_relate_mongodb(juju: JujuFixture, cloud_name: str):
    """Test the relation with MongoDB and database accessibility."""
    gather(
        juju.ext.model.deploy(
            MONGODB[cloud_name],
            channel="6/edge",
            application_name=MONGODB[cloud_name],
            num_units=1,
            series="jammy",
            trust=True,
        )
    )
    juju.ext.model.wait_for_idle(apps=[MONGODB[cloud_name]], wait_for_active=True)
    assert juju.ext.model.applications[MONGODB[cloud_name]].status == "active"
    integrator_relation = juju.ext.model.add_relation(DATA_INTEGRATOR, MONGODB[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB[cloud_name]])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "active"

    # check if secrets are used on Juju3
    assert check_secrets_usage_matching_juju_version(
        juju,
        juju.ext.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )

    # get credential for MongoDB
    credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {MONGODB[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "create-table",
        MONGODB[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {MONGODB[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "insert-data",
        MONGODB[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {MONGODB[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        MONGODB[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    # drop relation and get new credential for the same collection
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB[cloud_name]}:database"
    )

    juju.ext.model.wait_for_idle(apps=[MONGODB[cloud_name], DATA_INTEGRATOR])
    juju.ext.model.add_relation(DATA_INTEGRATOR, MONGODB[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, MONGODB[cloud_name]])

    new_credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    # test that different credentials are provided
    assert credentials != new_credentials

    logger.info(
        f"Check assessibility of inserted data on {MONGODB[cloud_name]} with new credentials"
    )
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        MONGODB[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mongodb", f"{MONGODB[cloud_name]}:database"
    )

    juju.ext.model.wait_for_idle(apps=[MONGODB[cloud_name], DATA_INTEGRATOR])
