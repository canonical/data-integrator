#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import boto3
import boto3.session
import pytest
import pytest_microceph
from botocore.client import Config
from pytest_operator.plugin import OpsTest

TEST_BUCKET_NAME = "kyuubi-test"
TEST_PATH_NAME = "spark-events/"


logger = logging.getLogger(__name__)


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


@pytest.fixture(scope="module")
def s3_bucket_and_creds(ops_test: OpsTest, microceph: pytest_microceph.ConnectionInformation):
    if ops_test.model.info.provider_type != "kubernetes":
        yield None
        return

    endpoint_url = "http://localhost"
    access_key = microceph.access_key_id
    secret_key = microceph.secret_access_key
    bucket_name = microceph.bucket

    session = boto3.session.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    s3 = session.resource(
        service_name="s3",
        endpoint_url=endpoint_url,
        verify=False,
        config=Config(connect_timeout=60, retries={"max_attempts": 4}),
    )
    test_bucket = s3.Bucket(bucket_name)
    test_bucket.put_object(Key=TEST_PATH_NAME)

    yield {
        "endpoint": endpoint_url,
        "access_key": access_key,
        "secret_key": secret_key,
        "bucket": bucket_name,
        "path": TEST_PATH_NAME,
    }

    logger.info("Tearing down test bucket...")
    test_bucket.objects.all().delete()
    test_bucket.delete()
