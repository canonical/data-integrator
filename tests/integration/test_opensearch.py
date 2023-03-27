#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import re
import tempfile
from pathlib import PosixPath

import pytest
import requests
from pytest_operator.plugin import OpsTest

from .constants import (
    DATA_INTEGRATOR,
    INDEX_NAME,
    OPENSEARCH,
    OPENSEARCH_EXTRA_USER_ROLES,
    TLS_CERTIFICATES_APP_NAME,
)
from .helpers import fetch_action_get_credentials

logger = logging.getLogger(__name__)


def opensearch_request(ops_test, credentials, method, endpoint, payload=None):
    """Send a request to the opensearch charm using the given credentials and parameters."""
    host = ops_test.model.applications[OPENSEARCH[ops_test.cloud_name]].units[0].public_address
    credentials = credentials.get(OPENSEARCH[ops_test.cloud_name])
    logger.error(credentials)
    with requests.Session() as s, tempfile.NamedTemporaryFile(mode="w+") as chain:
        chain.write(credentials.get("tls-ca"))
        chain.seek(0)

        s.auth = (credentials.get("username"), credentials.get("password"))
        resp = s.request(
            verify=False,
            method=method,
            url=f"https://{host}:9200{endpoint}",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            **{"data": payload} if payload else {},
        )
        resp.raise_for_status()
        return resp.json()


@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest, data_integrator_charm: PosixPath):
    """Deploys charms for testing.

    Note for developers, if deploying opensearch fails with some kernel parameter not set, run the
    following command:

    ```
    sudo sysctl -w vm.max_map_count=262144 vm.swappiness=0 net.ipv4.tcp_retries2=5
    ```
    """
    if ops_test.cloud_name != "localhost":
        pytest.skip("opensearch does not have a k8s charm yet.")

    tls_config = {"generate-self-signed-certificates": "true", "ca-common-name": "CN_CA"}
    # Set kernel params in model config opensearch can run
    model_config = {
        "logging-config": "<root>=INFO;unit=DEBUG",
        "update-status-hook-interval": "1m",
        "cloudinit-userdata": """postruncmd:
            - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
            - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
            - [ 'sysctl', '-w', 'vm.swappiness=0' ]
            - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
        """,
    }
    await ops_test.model.set_config(model_config)

    await asyncio.gather(
        ops_test.model.deploy(
            OPENSEARCH[ops_test.cloud_name],
            channel="edge",
            application_name=OPENSEARCH[ops_test.cloud_name],
            num_units=3,
        ),
        ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="edge", config=tls_config),
        ops_test.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        ),
    )
    config = {"index-name": INDEX_NAME, "extra-user-roles": OPENSEARCH_EXTRA_USER_ROLES}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config),
    await asyncio.gather(
        ops_test.model.relate(OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME),
        ops_test.model.relate(DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name]),
    )
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME],
        status="active",
        idle_period=10,
    )


async def test_sending_requests_using_opensearch(ops_test: OpsTest):
    """Verifies intended use case of data-integrator charm.

    This test verifies that we can use the credentials provided to the data-integrator charm to
    update and retrieve data from the opensearch charm.
    """
    if ops_test.cloud_name != "localhost":
        pytest.skip("opensearch does not have a k8s charm yet.")

    # get credentials for opensearch
    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.error(credentials)

    bulk_payload = """{ "index" : { "_index": "albums", "_id" : "1" } }
{"artist": "Herbie Hancock", "genre": ["Jazz"],  "title": "Head Hunters"}
{ "index" : { "_index": "albums", "_id" : "2" } }
{"artist": "Lydian Collective", "genre": ["Jazz"],  "title": "Adventure"}
{ "index" : { "_index": "albums", "_id" : "3" } }
{"artist": "Liquid Tension Experiment", "genre": ["Prog", "Metal"],  "title": "Liquid Tension Experiment 2"}
"""
    bulk_post = opensearch_request(
        ops_test, credentials, "POST", endpoint="/_bulk", payload=re.escape(bulk_payload)
    )
    logger.error(bulk_post)
    get_jazz = opensearch_request(ops_test, credentials, "GET", endpoint="/albums/_search?q=Jazz")
    logger.error(get_jazz)
    artists = [
        hit.get("_source", {}).get("artist") for hit in get_jazz.get("hits", {}).get("hits", [{}])
    ]
    assert set(artists) == {"Herbie Hancock", "Lydian Collective"}


async def test_recycle_credentials(ops_test: OpsTest):
    """Tests that we can recreate credentials by removing and creating a new relation."""
    if ops_test.cloud_name != "localhost":
        pytest.skip("opensearch does not have a k8s charm yet.")

    old_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )

    # Recreate relation to generate new credentials
    await ops_test.model.applications[OPENSEARCH[ops_test.cloud_name]].remove_relation(
        f"{OPENSEARCH[ops_test.cloud_name]}:opensearch-client", DATA_INTEGRATOR
    )
    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME],
            status="active",
            idle_period=10,
        ),
        ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR], status="blocked"),
    )

    await ops_test.model.relate(DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name]),
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME],
        status="active",
        idle_period=10,
    )

    # get new credentials for opensearch
    new_credentials = await fetch_action_get_credentials(
        ops_test.model.applications[DATA_INTEGRATOR].units[0]
    )
    logger.error(new_credentials)

    get_jazz_again = opensearch_request(
        ops_test, new_credentials, "GET", endpoint="/albums/_search?q=Jazz"
    )
    logger.error(get_jazz_again)
    artists = [
        hit.get("_source", {}).get("artist")
        for hit in get_jazz_again.get("hits", {}).get("hits", [{}])
    ]
    assert set(artists) == {"Herbie Hancock", "Lydian Collective"}

    # Old credentials should have been revoked.
    with pytest.raises(requests.HTTPError):
        opensearch_request(ops_test, old_credentials, "GET", endpoint="")
