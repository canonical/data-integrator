#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the mlflow relation (data-integrator requirer, MLflow provider).

These tests exercise the requirer side of the mlflow_client interface. Unlike most of the
data-integrator backends, MLflow is a Kubernetes charm, so this suite targets a Kubernetes
substrate (like the *-k8s backends) and requires the `mlflow-server` charm to expose the
`mlflow-client` relation (the provider side). They assert that, once related, the data-integrator
surfaces the MLflow username it requested (externally authenticated, hence password-less) and the
per-workspace grants it was given, and that editing the grants config takes effect without
recreating the relation.
"""

import asyncio
import json
import logging
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from .constants import (
    DATA_INTEGRATOR,
    MLFLOW,
    MLFLOW_ENTITY_NAME,
    MLFLOW_ENTITY_PERMISSIONS,
    MLFLOW_ENTITY_PERMISSIONS_UPDATED,
    MLFLOW_TIER,
    MLFLOW_TIER_UPDATED,
    MLFLOW_WORKSPACE_NAME,
    MLFLOW_WORKSPACE_NAME_UPDATED,
)
from .helpers import fetch_action_get_credentials
from .markers import only_on_k8s

logger = logging.getLogger(__name__)

MINIO = "minio"
POSTGRESQL_K8S = "postgresql-k8s"


@only_on_k8s
@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest, data_integrator_charm: PosixPath, cloud_name: str):
    """Deploy the data-integrator and request an MLflow user with a per-workspace grant."""
    await ops_test.model.deploy(
        data_integrator_charm, application_name=DATA_INTEGRATOR, num_units=1
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR], idle_period=30)
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"

    await ops_test.model.applications[DATA_INTEGRATOR].set_config({
        "entity-name": MLFLOW_ENTITY_NAME,
        "entity-permissions": MLFLOW_ENTITY_PERMISSIONS,
    })

    # without a relation the integrator stays blocked, asking to be related to the desired product:
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR], raise_on_error=False, status="blocked", idle_period=60
    )
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"


@only_on_k8s
@pytest.mark.abort_on_fail
async def test_deploy_and_relate_mlflow(ops_test: OpsTest, cloud_name: str):
    """Bring up the MLflow tracking server and relate the data-integrator to it."""
    await asyncio.gather(
        ops_test.model.deploy(
            MINIO,
            channel="latest/edge",
            config={"access-key": "minio", "secret-key": "minio123"},
            trust=True,
        ),
        ops_test.model.deploy(
            POSTGRESQL_K8S, channel="14/stable", config={"profile": "testing"}, trust=True
        ),
        # TODO: restore once https://github.com/canonical/mlflow-operator/pull/494 lands on main,
        # that is on channel "latest/edge", as python-libjuju breaks with this channel format:
        ops_test.juju("deploy", MLFLOW, "--channel", "latest/edge/pr-490", "--trust"),
        # ops_test.model.deploy(MLFLOW, channel="latest/edge", trust=True),
    )
    await ops_test.model.wait_for_idle(
        apps=[MINIO, POSTGRESQL_K8S], status="active", raise_on_blocked=False, timeout=1000
    )
    await ops_test.model.integrate(f"{MINIO}:object-storage", MLFLOW)
    await ops_test.model.integrate(POSTGRESQL_K8S, MLFLOW)
    await ops_test.model.wait_for_idle(apps=[MLFLOW], status="active", timeout=1000)

    await ops_test.model.integrate(f"{DATA_INTEGRATOR}:mlflow", f"{MLFLOW}:mlflow-client")
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, MLFLOW], status="active", idle_period=30, timeout=1000
    )


@only_on_k8s
@pytest.mark.abort_on_fail
async def test_get_credentials(ops_test: OpsTest, cloud_name: str):
    """The integrator surfaces the provisioned MLflow username and per-workspace grants."""
    result = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    assert result["ok"]
    credentials = result["mlflow"]
    assert credentials["username"] == MLFLOW_ENTITY_NAME
    assert json.loads(credentials["grants"]) == {MLFLOW_WORKSPACE_NAME: MLFLOW_TIER}


@only_on_k8s
@pytest.mark.abort_on_fail
async def test_edit_grants_without_recreating_relation(ops_test: OpsTest, cloud_name: str):
    """Editing the grants config is pushed to the live relation, without recreating it."""
    await ops_test.model.applications[DATA_INTEGRATOR].set_config({
        "entity-permissions": MLFLOW_ENTITY_PERMISSIONS_UPDATED,
    })
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, MLFLOW], status="active", idle_period=30, timeout=1000
    )

    result = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    credentials = result["mlflow"]
    assert credentials["username"] == MLFLOW_ENTITY_NAME
    assert json.loads(credentials["grants"]) == {
        MLFLOW_WORKSPACE_NAME_UPDATED: MLFLOW_TIER_UPDATED
    }
