#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import socket
import uuid
from pathlib import Path

import pytest
import pytest_microceph
from pytest_operator.plugin import OpsTest
from spark_test.core.s3 import Credentials

TEST_BUCKET_NAME = "kyuubi-test"
TEST_PATH_NAME = "spark-events/"
HOST_IP = socket.gethostbyname(socket.gethostname())


logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
async def data_integrator_charm(ops_test: OpsTest) -> Path:
    """Kafka charm used for integration testing."""
    try:
        charm = await ops_test.build_charm(".")
    except Exception as e:
        logger.error(e)
        return Path()
    return charm


@pytest.fixture(scope="module")
async def app_charm(ops_test: OpsTest):
    """Build the application charm."""
    charm_path = "tests/integration/app-charm"
    try:    
        charm = await ops_test.build_charm(charm_path)
    except Exception as e:
        logger.error(e)
        return Path()
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


@pytest.fixture(scope="module")
def bucket_name():
    """S3 Bucket name."""
    return f"s3-bucket-{uuid.uuid4()}"


@pytest.fixture(scope="module")
def credentials(microceph: pytest_microceph.ConnectionInformation):
    """S3 credentials to connect to S3 storage."""
    yield Credentials(
        access_key=microceph.access_key_id, secret_key=microceph.secret_access_key, host=HOST_IP
    )
