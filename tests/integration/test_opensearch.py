#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import re
import time
from pathlib import PosixPath

import pytest
from pytest_operator.plugin import OpsTest

from .constants import (
    APP,
    DATA_INTEGRATOR,
    INDEX_NAME,
    OPENSEARCH,
    OPENSEARCH_EXTRA_USER_ROLES,
    TLS_CERTIFICATES_APP_NAME,
)
from .helpers import (
    check_secrets_usage_matching_juju_version,
    fetch_action_get_credentials,
)

logger = logging.getLogger(__name__)


async def run_request(
    ops_test,
    unit_name: str,
    method: str,
    endpoint: str,
    credentials: str,
    payload: str = None,
    timeout: int = 30,
):
    kwargs = {"payload": payload} if payload else {}

    client_unit = ops_test.model.units.get(unit_name)
    action = await client_unit.run_action(
        action_name="http-request",
        unit_name=unit_name,
        method=method,
        endpoint=endpoint,
        credentials=credentials,
        **kwargs,
    )
    result = await asyncio.wait_for(action.wait(), timeout)
    return result.results


@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest, app_charm: PosixPath, data_integrator_charm: PosixPath):
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
        ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="stable", config=tls_config),
        ops_test.model.deploy(
            data_integrator_charm, application_name="data-integrator", num_units=1, series="jammy"
        ),
        ops_test.model.deploy(app_charm, application_name=APP, num_units=1, series="jammy"),
    )
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME],
        idle_period=10,
        timeout=1600,
    )
    config = {"index-name": INDEX_NAME, "extra-user-roles": OPENSEARCH_EXTRA_USER_ROLES}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)
    await ops_test.model.relate(OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME)
    integrator_relation = await ops_test.model.relate(
        DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name]
    )

    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME, APP],
        status="active",
        idle_period=10,
        timeout=1600,
    )

    # check if secrets are used on Juju3
    assert await check_secrets_usage_matching_juju_version(
        ops_test,
        ops_test.model.applications[DATA_INTEGRATOR].units[0].name,
        integrator_relation.id,
    )


async def test_sending_requests_using_opensearch(ops_test: OpsTest):
    """Verifies intended use case of data-integrator charm.

    This test verifies that we can use the credentials provided to the data-integrator charm to
    update and retrieve data from the opensearch charm.
    """
    if ops_test.cloud_name != "localhost":
        pytest.skip("opensearch does not have a k8s charm yet.")

    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME, APP],
        status="active",
        idle_period=30,
        timeout=1000,
    )

    # get credentials for opensearch
    credentials = (
        await fetch_action_get_credentials(ops_test.model.applications[DATA_INTEGRATOR].units[0])
    ).get(OPENSEARCH[ops_test.cloud_name])
    logger.error(credentials)

    # This request can be temperamental, because opensearch can appear active without having
    # available databases.
    put_vulf = await run_request(
        ops_test,
        unit_name=ops_test.model.applications[APP].units[0].name,
        method="PUT",
        endpoint="/albums/_doc/1",
        payload=re.escape(
            '{"artist": "Vulfpeck", "genre": ["Funk", "Jazz"], "title": "Thrill of the Arts"}'
        ),
        credentials=json.dumps(credentials),
    )
    logger.error(put_vulf)

    # Wait for `albums` index to refresh so the data is searchable
    time.sleep(30)

    get_jazz = json.loads(
        (
            await run_request(
                ops_test,
                unit_name=ops_test.model.applications[APP].units[0].name,
                method="GET",
                endpoint="/albums/_search?q=Jazz",
                credentials=json.dumps(credentials),
            )
        ).get("results")
    )
    artists = [
        hit.get("_source", {}).get("artist") for hit in get_jazz.get("hits", {}).get("hits", [{}])
    ]
    assert set(artists) == {"Vulfpeck"}


async def test_recycle_credentials(ops_test: OpsTest):
    """Tests that we can recreate credentials by removing and creating a new relation."""
    if ops_test.cloud_name != "localhost":
        pytest.skip("opensearch does not have a k8s charm yet.")

    old_credentials = (
        await fetch_action_get_credentials(ops_test.model.applications[DATA_INTEGRATOR].units[0])
    ).get(OPENSEARCH[ops_test.cloud_name])

    # Recreate relation to generate new credentials
    await ops_test.model.applications[OPENSEARCH[ops_test.cloud_name]].remove_relation(
        f"{OPENSEARCH[ops_test.cloud_name]}:opensearch-client", DATA_INTEGRATOR
    )
    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME, APP],
            status="active",
            idle_period=10,
        ),
        ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR], status="blocked"),
    )

    await ops_test.model.relate(DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name]),
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR, OPENSEARCH[ops_test.cloud_name], TLS_CERTIFICATES_APP_NAME, APP],
        status="active",
        idle_period=10,
    )

    # get new credentials for opensearch
    new_credentials = (
        await fetch_action_get_credentials(ops_test.model.applications[DATA_INTEGRATOR].units[0])
    ).get(OPENSEARCH[ops_test.cloud_name])
    logger.error(new_credentials)

    get_jazz_again = json.loads(
        (
            await run_request(
                ops_test,
                unit_name=ops_test.model.applications[APP].units[0].name,
                method="GET",
                endpoint="/albums/_search?q=Jazz",
                credentials=json.dumps(new_credentials),
            )
        ).get("results")
    )
    logger.error(get_jazz_again)
    artists = [
        hit.get("_source", {}).get("artist")
        for hit in get_jazz_again.get("hits", {}).get("hits", [{}])
    ]
    assert set(artists) == {"Vulfpeck"}

    # Old credentials should have been revoked.
    bad_request_resp = json.loads(
        (
            await run_request(
                ops_test,
                unit_name=ops_test.model.applications[APP].units[0].name,
                method="GET",
                endpoint="/albums/_search?q=Jazz",
                credentials=json.dumps(old_credentials),
            )
        ).get("results")
    )
    assert bad_request_resp.get("status_code") == 401, bad_request_resp
