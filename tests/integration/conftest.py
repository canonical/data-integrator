#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import os
import socket
import subprocess
import time
import uuid

import boto3
import botocore
import pytest
from jubilant_adapters import JujuFixture, temp_model_fixture
from spark_test.core.s3 import Credentials

from .architecture import architecture

TEST_BUCKET_NAME = "kyuubi-test"
TEST_PATH_NAME = "spark-events/"
HOST_IP = socket.gethostbyname(socket.gethostname())

_BUCKET = "testbucket"

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    """Defines pytest parsers."""
    parser.addoption(
        "--model",
        action="store",
        help="Juju model to use; if not provided, a new model "
        "will be created for each test which requires one",
    )
    parser.addoption(
        "--keep-models",
        action="store_true",
        help="Keep models handled by opstest, can be overridden in track_model",
    )


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest):
    """Pytest fixture that wraps :meth:`jubilant.with_model`.

    This adds command line parameter ``--keep-models`` (see help for details).
    """
    model = request.config.getoption("--model")
    keep_models = bool(request.config.getoption("--keep-models"))

    if model:
        try:
            JujuFixture().add_model(model, config={"update-status-hook-interval": "60s"})
        except Exception as e:
            if "already exists" not in str(e):
                raise e
            # Keep model anyway if it already exists.
            keep_models = True
        logger.warning(f"Model{model} already exists, reusing")
        juju = JujuFixture(model=model)
        yield juju
    else:
        with temp_model_fixture(keep=keep_models) as juju:
            yield juju


@pytest.fixture(scope="module", autouse=True)
def setup_juju(juju: JujuFixture):
    if not juju.model:
        return

    juju.wait_timeout = 600.0
    juju.cli("switch", juju.model, include_model=False)


@pytest.fixture(scope="module")
def data_integrator_charm() -> str:
    """Kafka charm used for integration testing."""
    return f"./data-integrator_ubuntu@22.04-{architecture}.charm"


@pytest.fixture(scope="module")
def app_charm() -> str:
    """Build the application charm."""
    return f"./tests/integration/app-charm/application_ubuntu@22.04-{architecture}.charm"


@pytest.fixture()
def cloud_name(juju: JujuFixture, request):
    """Checks the cloud."""
    if request.node.parent:
        marks = [m.name for m in request.node.iter_markers()]
    else:
        marks = []
    models_raw = juju.cli("models", "--format", "json", include_model=False)
    models_json = json.loads(models_raw)
    type_ = models_json["models"][0]["type"]
    if type_ == "kubernetes":
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
def credentials():
    """S3 credentials to connect to S3 storage."""
    if not os.environ.get("CI") == "true":
        raise Exception("Not running on CI. Skipping microceph installation")
    logger.info("Setting up microceph")
    subprocess.run(["sudo", "snap", "install", "microceph"], check=True)
    subprocess.run(["sudo", "microceph", "cluster", "bootstrap"], check=True)
    subprocess.run(["sudo", "microceph", "disk", "add", "loop,1G,3"], check=True)
    subprocess.run(["sudo", "microceph", "enable", "rgw"], check=True)
    output = subprocess.run(
        [
            "sudo",
            "microceph.radosgw-admin",
            "user",
            "create",
            "--uid",
            "test",
            "--display-name",
            "test",
        ],
        capture_output=True,
        check=True,
        encoding="utf-8",
    ).stdout
    key = json.loads(output)["keys"][0]
    key_id = key["access_key"]
    secret_key = key["secret_key"]
    logger.info("Creating microceph bucket")
    for attempt in range(3):
        try:
            boto3.client(
                "s3",
                endpoint_url="http://localhost",
                aws_access_key_id=key_id,
                aws_secret_access_key=secret_key,
            ).create_bucket(Bucket=_BUCKET)
        except botocore.exceptions.EndpointConnectionError:
            if attempt == 2:
                raise
            # microceph is not ready yet
            logger.info("Unable to connect to microceph via S3. Retrying")
            time.sleep(1)
        else:
            break
    logger.info("Set up microceph")
    yield Credentials(access_key=key_id, secret_key=secret_key, host=HOST_IP)
