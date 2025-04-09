#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import PosixPath

import pytest
from juju.application import Application
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

from .constants import (
    APP,
    DATA_INTEGRATOR,
    ETCD,
    TLS_CERTIFICATES_APP_NAME,
)
from .helpers import check_secrets_usage_matching_juju_version
from .markers import only_on_localhost, only_with_juju_secrets

logger = logging.getLogger(__name__)


@pytest.mark.group(1)
@only_on_localhost
@only_with_juju_secrets
@pytest.mark.abort_on_fail
async def test_deploy(
    ops_test: OpsTest, app_charm: PosixPath, data_integrator_charm: PosixPath, cloud_name: str
):
    """Deploys charms for testing."""
    tls_config = {"ca-common-name": "CN_CA"}
    model_config = {
        "logging-config": "<root>=INFO;unit=DEBUG",
    }
    await ops_test.model.set_config(model_config)

    await asyncio.gather(
        ops_test.model.deploy(
            ETCD[cloud_name],
            channel="3.5/edge",
            application_name=ETCD[cloud_name],
            num_units=3,
        ),
        ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="1/stable", config=tls_config),
        ops_test.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        ),
        ops_test.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    await ops_test.model.integrate(
        f"{ETCD[cloud_name]}:peer-certificates", TLS_CERTIFICATES_APP_NAME
    )
    await ops_test.model.integrate(
        f"{ETCD[cloud_name]}:client-certificates", TLS_CERTIFICATES_APP_NAME
    )
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, ETCD[cloud_name], TLS_CERTIFICATES_APP_NAME, APP],
        idle_period=10,
        timeout=1600,
    )


@pytest.mark.group(1)
@only_on_localhost
@only_with_juju_secrets
@pytest.mark.abort_on_fail
async def test_relate(ops_test: OpsTest, cloud_name: str):
    """Relates the charms."""
    # generate a certificate using app-charm
    app: Application = ops_test.model.applications[APP]
    app_unit: Unit = app.units[0]

    # generate cert in the app charm
    action = await app_unit.run_action("generate-cert", **{"common-name": "test-common-name"})
    action = await action.wait()
    assert action.status == "completed"

    certificate, key = action.results["certificate"], action.results["key"]
    assert certificate, "The certificate is not generated."
    assert key, "The key is not generated."

    # configure the data-integrator charm with the certificate
    config = {"mtls-cert": certificate, "prefix-name": "/test/"}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # relate the data-integrator charm with the etcd charm
    integrator_relation = await ops_test.model.integrate(DATA_INTEGRATOR, ETCD[cloud_name])

    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, ETCD[cloud_name], TLS_CERTIFICATES_APP_NAME, APP],
        status="active",
        idle_period=10,
        timeout=1600,
    )

    # run get credentials action on data-integrator
    action = (
        await ops_test.model.applications[DATA_INTEGRATOR].units[0].run_action("get-credentials")
    )
    action = await action.wait()
    assert action.status == "completed"

    results = action.results
    assert "etcd" in results
    for key in ["prefix", "tls-ca", "username", "version", "endpoints"]:
        assert key in results["etcd"]
    assert results["etcd"]["username"] == "test-common-name"

    # check if secrets are used on Juju3
    assert await check_secrets_usage_matching_juju_version(
        ops_test,
        ops_test.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )


@pytest.mark.group(1)
@only_on_localhost
@only_with_juju_secrets
@pytest.mark.abort_on_fail
async def test_read_write(ops_test: OpsTest, cloud_name: str):
    """Write and read to the key prefix with the requirer charm."""
    # get endpoints
    # run get credentials action on data-integrator
    action = (
        await ops_test.model.applications[DATA_INTEGRATOR].units[0].run_action("get-credentials")
    )
    action = await action.wait()
    assert action.status == "completed"
    credentials = {
        "endpoints": action.results["etcd"]["endpoints"],
        "tls-ca": action.results["etcd"]["tls-ca"],
    }
    params = {
        "product": "etcd",
        "database-name": "/test",
        "credentials": json.dumps(credentials),
    }
    # # write to the key prefix
    app: Application = ops_test.model.applications[APP]
    app_unit: Unit = app.units[0]

    action = await app_unit.run_action("insert-data", **params)
    action = await action.wait()
    assert action.status == "completed"
    assert action.results["ok"] == "True"

    # read from the key prefix
    action = await app_unit.run_action("check-inserted-data", **params)
    action = await action.wait()
    assert action.status == "completed"
    assert action.results["ok"] == "True"
