#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import logging
from pathlib import PosixPath

from jubilant_adapters import JujuFixture, gather

from .constants import APP, DATA_INTEGRATOR, DATABASE_NAME, MYSQL, MYSQL_ROUTER
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
    logger.info(f"Wait for blocked status for {DATA_INTEGRATOR}")
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"

    logger.info(f"Configure database name: {DATABASE_NAME}")
    config = {"database-name": DATABASE_NAME}
    juju.ext.model.applications[DATA_INTEGRATOR].set_config(config)

    logger.info("Test the blocked status for relation with database name set")
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"


def test_deploy_and_relate_mysql(juju: JujuFixture, cloud_name: str):
    """Test the relation with MySQL and database accessibility."""
    gather(
        juju.ext.model.deploy(
            MYSQL[cloud_name],
            channel="8.0/edge",
            application_name=MYSQL[cloud_name],
            num_units=1,
            series="jammy",
            trust=True,
            config={"profile": "testing"},
        )
    )
    juju.ext.model.wait_for_idle(apps=[MYSQL[cloud_name]], status="active")
    assert juju.ext.model.applications[MYSQL[cloud_name]].status == "active"
    integrator_relation = juju.ext.model.add_relation(DATA_INTEGRATOR, MYSQL[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL[cloud_name]])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "active"

    # check if secrets are used on Juju3
    assert check_secrets_usage_matching_juju_version(
        juju,
        juju.ext.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )

    # get credential for MYSQL
    logger.info(f"Get credential for {MYSQL[cloud_name]}")
    credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info(f"Create table on {MYSQL[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "create-table",
        MYSQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {MYSQL[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "insert-data",
        MYSQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {MYSQL[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        MYSQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info("Remove relation and test connection again")
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{MYSQL[cloud_name]}:database"
    )

    juju.ext.model.wait_for_idle(apps=[MYSQL[cloud_name], DATA_INTEGRATOR])
    juju.ext.model.add_relation(DATA_INTEGRATOR, MYSQL[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL[cloud_name]])

    logger.info("Join with new relation and check the previously created database")
    new_credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(
        f"Check assessibility of inserted data on {MYSQL[cloud_name]} with new credentials"
    )
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        MYSQL[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Unlock (unreleate) {DATA_INTEGRATOR} for mysql-router tests")
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{MYSQL[cloud_name]}:database"
    )
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL[cloud_name]])


def test_deploy_and_relate_mysql_router(juju: JujuFixture, cloud_name: str):
    """Test the relation with mysql-router and database accessibility."""
    logger.info(f"Test the relation with {MYSQL_ROUTER[cloud_name]}.")
    num_units = 0 if cloud_name == "localhost" else 1
    channel = "dpe/edge" if cloud_name == "localhost" else "8.0/edge"
    gather(
        juju.ext.model.deploy(
            MYSQL_ROUTER[cloud_name],
            application_name=MYSQL_ROUTER[cloud_name],
            channel=channel,
            num_units=num_units,
            series="jammy",
            trust=True,
        ),
    )
    juju.ext.model.add_relation(MYSQL[cloud_name], MYSQL_ROUTER[cloud_name])
    juju.ext.model.add_relation(f"{DATA_INTEGRATOR}:mysql", f"{MYSQL_ROUTER[cloud_name]}:database")
    juju.ext.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, MYSQL[cloud_name], MYSQL_ROUTER[cloud_name]],
        status="active",
    )
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "active"

    logger.info(f"Get credential for {MYSQL_ROUTER[cloud_name]}")
    credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    logger.info(f"Create table on {MYSQL_ROUTER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "create-table",
        MYSQL_ROUTER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {MYSQL_ROUTER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "insert-data",
        MYSQL_ROUTER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check assessibility of inserted data on {MYSQL_ROUTER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        MYSQL_ROUTER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info("Remove relation and test connection again")
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:mysql", f"{MYSQL_ROUTER[cloud_name]}:database"
    )
    # Subordinate charm will be removed and wait_for_idle expects the app to have units
    if cloud_name == "localhost":
        idle_apps = [DATA_INTEGRATOR]
    else:
        idle_apps = [DATA_INTEGRATOR, MYSQL_ROUTER[cloud_name]]

    juju.ext.model.wait_for_idle(apps=idle_apps)
    juju.ext.model.add_relation(DATA_INTEGRATOR, MYSQL_ROUTER[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, MYSQL_ROUTER[cloud_name]])

    logger.info("Relate and check the accessibility of the previously created database")
    new_credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(f"Check inserted data on {MYSQL_ROUTER[cloud_name]} with new credentials")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        MYSQL_ROUTER[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
