#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess
from pathlib import Path

import boto3
import boto3.session
import pytest
from botocore.client import Config
from pytest_operator.plugin import OpsTest

from .markers import only_on_microk8s

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


@only_on_microk8s
@pytest.fixture()
def s3_bucket_and_creds(cloud_name: str):
    logger.info("Fetching S3 credentials from minio.....")

    fetch_s3_output = (
        subprocess.check_output(
            "./tests/integration/scripts/fetch_s3_credentials.sh | tail -n 3",
            shell=True,
            stderr=None,
        )
        .decode("utf-8")
        .strip()
    )

    logger.info(f"fetch_s3_credentials output:\n{fetch_s3_output}")

    endpoint_url, access_key, secret_key = fetch_s3_output.strip().splitlines()

    session = boto3.session.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    s3 = session.resource(
        service_name="s3",
        endpoint_url=endpoint_url,
        verify=False,
        config=Config(connect_timeout=60, retries={"max_attempts": 4}),
    )
    test_bucket = s3.Bucket(TEST_BUCKET_NAME)

    # Delete test bucket if it exists
    if test_bucket in s3.buckets.all():
        logger.info(f"The bucket {TEST_BUCKET_NAME} already exists. Deleting it...")
        test_bucket.objects.all().delete()
        test_bucket.delete()

    # Create the test bucket
    s3.create_bucket(Bucket=TEST_BUCKET_NAME)
    logger.info(f"Created bucket: {TEST_BUCKET_NAME}")
    test_bucket.put_object(Key=TEST_PATH_NAME)
    yield {
        "endpoint": endpoint_url,
        "access_key": access_key,
        "secret_key": secret_key,
        "bucket": TEST_BUCKET_NAME,
        "path": TEST_PATH_NAME,
    }

    logger.info("Tearing down test bucket...")
    test_bucket.objects.all().delete()
    test_bucket.delete()
