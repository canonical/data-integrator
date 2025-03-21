# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import importlib.metadata

import juju.unit

# libjuju version != juju agent version, but the major version should be identical—which is good
# enough to check for secrets
_libjuju_version = importlib.metadata.version("juju")
has_secrets = int(_libjuju_version.split(".")[0]) >= 3
is_juju_3 = int(_libjuju_version.split(".")[0]) >= 3


async def run_action(unit: juju.unit.Unit, action_name, **params):
    action = await unit.run_action(action_name=action_name, **params)
    result = await action.wait()
    # Syntax changed across libjuju major versions
    if int(_libjuju_version.split(".")[0]) <= 2:
        assert result.results.get("Code") == "0"
    else:
        assert result.results.get("return-code") == 0
    return result.results
