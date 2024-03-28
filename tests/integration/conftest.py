#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest


@pytest.fixture(scope="module")
async def data_integrator_charm(ops_test: OpsTest) -> Path:
    """Kafka charm used for integration testing."""
    charm = await ops_test.build_charm(".")
    return charm


@pytest.fixture(scope="module")
async def app_charm(ops_test: OpsTest):
    """Build the application charm."""
    charm_path = "tests/integration/app-charm"
    charm = await ops_test.build_charm(charm_path)
    return charm


@pytest.fixture()
async def cloud_name(ops_test: OpsTest, request):
    """Checks the cloud."""
    if request.node.parent:
        marks = [m.name for m in request.node.iter_markers()]
    else:
        marks = []
    if ops_test.model.info.provider_type == "kubernetes":
        if "only_on_localhost" in marks:
            pytest.skip("Does not run on k8s")
            return
        return "microk8s"
    else:
        if "only_on_microk8s" in marks:
            pytest.skip("Does not run on vm")
            return
        return "localhost"
