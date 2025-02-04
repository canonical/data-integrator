# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest

from . import juju_

only_with_juju_secrets = pytest.mark.skipif(
    not juju_.has_secrets, reason="Requires juju version w/secrets"
)
only_without_juju_secrets = pytest.mark.skipif(
    juju_.has_secrets, reason="Requires juju version w/o secrets"
)
only_with_juju_3 = pytest.mark.skipif(juju_.is_juju_3, reason="Requires juju version >= 3")

# Skipped in the cloud_name fixture
only_on_localhost = pytest.mark.only_on_localhost
only_on_microk8s = pytest.mark.only_on_microk8s
