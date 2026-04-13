#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import logging
from pathlib import PosixPath
from time import sleep

from jubilant_adapters import JujuFixture, gather

from .constants import APP, DATA_INTEGRATOR, DATABASE_NAME, PGBOUNCER, POSTGRESQL
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

    config = {"database-name": DATABASE_NAME}
    juju.ext.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"


def test_deploy_and_relate_postgresql(juju: JujuFixture, cloud_name: str):
    """Test the relation with PostgreSQL and database accessibility."""
    gather(
        juju.ext.model.deploy(
            POSTGRESQL[cloud_name],
            channel="14/edge",
            application_name=POSTGRESQL[cloud_name],
            num_units=1,
            series="jammy",
            trust=True,
        )
    )
    juju.ext.model.wait_for_idle(
        apps=[POSTGRESQL[cloud_name]],
        status="active",
        timeout=1000,
    )
    assert juju.ext.model.applications[POSTGRESQL[cloud_name]].status == "active"
    juju.ext.model.add_relation(DATA_INTEGRATOR, POSTGRESQL[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL[cloud_name]], status="active")
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for PostgreSQL
    credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {POSTGRESQL[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "create-table",
        POSTGRESQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {POSTGRESQL[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "insert-data",
        POSTGRESQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check accessibility of inserted data on {POSTGRESQL[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        POSTGRESQL[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL[cloud_name]}:database"
    )

    juju.ext.model.wait_for_idle(apps=[POSTGRESQL[cloud_name], DATA_INTEGRATOR])
    integrator_relation = juju.ext.model.add_relation(DATA_INTEGRATOR, POSTGRESQL[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL[cloud_name]], status="active")

    # check if secrets are used on Juju3
    assert check_secrets_usage_matching_juju_version(
        juju,
        juju.ext.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )

    new_credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )
    assert credentials != new_credentials
    logger.info(
        f"Check accessibility of inserted data on {POSTGRESQL[cloud_name]} with new credentials"
    )
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        POSTGRESQL[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info(f"Unlock (unrelate) {DATA_INTEGRATOR} for the PgBouncer tests")
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL[cloud_name]}:database"
    )
    # Ensuring full cleanup of relation traces, avoiding failure on re-creating it soon
    sleep(3)


def test_deploy_and_relate_pgbouncer(juju: JujuFixture, cloud_name: str):
    """Test the relation with PgBouncer and database accessibility."""
    logger.info(f"Test the relation with {PGBOUNCER[cloud_name]}.")
    num_units = 0 if cloud_name == "localhost" else 1
    gather(
        juju.ext.model.deploy(
            PGBOUNCER[cloud_name],
            application_name=PGBOUNCER[cloud_name],
            channel="1/edge",
            num_units=num_units,
            series="jammy",
            trust=True,
        ),
    )

    juju.ext.model.add_relation(PGBOUNCER[cloud_name], POSTGRESQL[cloud_name])
    juju.ext.model.wait_for_idle(apps=[POSTGRESQL[cloud_name]], status="active")

    juju.ext.model.add_relation(PGBOUNCER[cloud_name], DATA_INTEGRATOR)
    juju.ext.model.wait_for_idle(apps=[PGBOUNCER[cloud_name], DATA_INTEGRATOR], status="active")

    logger.info(f"Get credential for {PGBOUNCER[cloud_name]}")
    credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.info(f"Create table on {PGBOUNCER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "create-table",
        PGBOUNCER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Insert data in the table on {PGBOUNCER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "insert-data",
        PGBOUNCER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
    logger.info(f"Check accessibility of inserted data on {PGBOUNCER[cloud_name]}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        PGBOUNCER[cloud_name],
        json.dumps(credentials),
        DATABASE_NAME,
    )
    assert result["ok"]

    logger.info("Remove relation and test connection again")
    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{PGBOUNCER[cloud_name]}:database"
    )

    # Subordinate charm will be removed and wait_for_idle expects the app to have units
    if cloud_name == "localhost":
        idle_apps = [DATA_INTEGRATOR]
    else:
        idle_apps = [DATA_INTEGRATOR, PGBOUNCER[cloud_name]]

    juju.ext.model.wait_for_idle(apps=idle_apps)
    juju.ext.model.add_relation(DATA_INTEGRATOR, PGBOUNCER[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, PGBOUNCER[cloud_name]], status="active")

    logger.info("Relate and check the accessibility of the previously created database")
    new_credentials = fetch_action_get_credentials(
        juju.ext.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert credentials != new_credentials
    logger.info(
        f"Check accessibility of inserted data on {PGBOUNCER[cloud_name]} with new credentials"
    )
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        PGBOUNCER[cloud_name],
        json.dumps(new_credentials),
        DATABASE_NAME,
    )
    assert result["ok"]
