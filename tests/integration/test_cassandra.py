#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import logging
from pathlib import PosixPath

from jubilant_adapters import JujuFixture, gather

from .constants import (
    APP,
    CASSANDRA,
    CASSANDRA_EXTRA_USER_ROLES,
    DATA_INTEGRATOR,
    KEYSPACE_NAME,
)
from .helpers import (
    fetch_action_database,
    fetch_action_get_credentials,
)
from .markers import only_on_localhost, only_with_juju_secrets

logger = logging.getLogger(__name__)


@only_on_localhost
@only_with_juju_secrets
def test_deploy(juju: JujuFixture, app_charm: PosixPath, data_integrator_charm: PosixPath):
    gather(
        juju.ext.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        ),
        juju.ext.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, APP], idle_period=30)
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"

    config = {"keyspace-name": KEYSPACE_NAME, "extra-user-roles": CASSANDRA_EXTRA_USER_ROLES}
    juju.ext.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/blocked status for relation
    juju.ext.model.wait_for_idle(
        apps=[DATA_INTEGRATOR],
        raise_on_error=False,
        status="blocked",
        idle_period=120,
    )
    assert juju.ext.model.applications[DATA_INTEGRATOR].status == "blocked"


@only_on_localhost
@only_with_juju_secrets
def test_deploy_and_relate_cassandra(juju: JujuFixture, cloud_name: str):
    """Test the relation with Kafka and the correct production and consumption of messagges."""
    gather(
        juju.ext.model.deploy(
            CASSANDRA[cloud_name],
            channel="5/edge",
            application_name=CASSANDRA[cloud_name],
            num_units=1,
        ),
    )

    juju.ext.model.wait_for_idle(apps=[CASSANDRA[cloud_name]], timeout=1000, status="active")

    juju.ext.model.add_relation(CASSANDRA[cloud_name], DATA_INTEGRATOR)
    juju.ext.model.wait_for_idle(
        apps=[CASSANDRA[cloud_name], DATA_INTEGRATOR],
        timeout=2000,
        idle_period=30,
        status="active",
    )


@only_on_localhost
@only_with_juju_secrets
def test_data_read_write_on_cassandra(juju: JujuFixture, cloud_name: str):
    """Test the database accessibility."""
    # get credential for Cassandra
    result = fetch_action_get_credentials(juju.ext.model.applications[DATA_INTEGRATOR].units[0])

    credentials = result[CASSANDRA[cloud_name]]

    logger.info(f"Create table on {CASSANDRA}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "create-table",
        CASSANDRA[cloud_name],
        json.dumps(credentials),
        KEYSPACE_NAME,
    )
    assert result["ok"]

    logger.info(f"Insert rows to table on {CASSANDRA}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "insert-data",
        CASSANDRA[cloud_name],
        json.dumps(credentials),
        KEYSPACE_NAME,
    )
    assert result["ok"]

    logger.info(f"Check assessibility of inserted data on {CASSANDRA}")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        CASSANDRA[cloud_name],
        json.dumps(credentials),
        KEYSPACE_NAME,
    )
    assert result["ok"]

    juju.ext.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:cassandra", f"{CASSANDRA[cloud_name]}:cassandra-client"
    )
    juju.ext.model.wait_for_idle(apps=[CASSANDRA[cloud_name], DATA_INTEGRATOR])

    juju.ext.model.add_relation(DATA_INTEGRATOR, CASSANDRA[cloud_name])
    juju.ext.model.wait_for_idle(apps=[DATA_INTEGRATOR, CASSANDRA[cloud_name]])

    result = fetch_action_get_credentials(juju.ext.model.applications[DATA_INTEGRATOR].units[0])

    new_credentials = result[CASSANDRA[cloud_name]]

    # test that different credentials are provided
    assert credentials != new_credentials

    logger.info(f"Check assessibility of inserted data on {CASSANDRA} with new credentials")
    result = fetch_action_database(
        juju.ext.model.applications[APP].units[0],
        "check-inserted-data",
        CASSANDRA[cloud_name],
        json.dumps(new_credentials),
        KEYSPACE_NAME,
    )
    assert result["ok"]
