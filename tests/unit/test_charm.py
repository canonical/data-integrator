# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from unittest.mock import MagicMock, Mock, patch

from charms.data_platform_libs.v0.data_interfaces import ENTITY_USER
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness

from charm import IntegratorCharm

BLOCKED_STATUS_INVALID_KF_TOPIC = BlockedStatus("Please pass an acceptable topic value")
BLOCKED_STATUS_NO_CONFIG = BlockedStatus(
    "Please specify either topic, index, database name, keyspace name, entity name, or prefix",
)
BLOCKED_STATUS_RELATE = BlockedStatus(
    "Please relate the data-integrator with the desired product",
)
BLOCKED_STATUS_REMOVE_DB = BlockedStatus(
    "To change database name: foo, please remove relation and add it again",
)
BLOCKED_STATUS_REMOVE_KF = BlockedStatus(
    "To change topic: bar, please remove relation and add it again",
)

juju_version = MagicMock()
juju_version.has_secrets = True


class TestCharm(unittest.TestCase):
    @patch("ops.jujuversion.JujuVersion.from_environ", return_value=juju_version)
    def setUp(self, _):
        self.harness = Harness(IntegratorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation(
            "data-integrator-peers", "data-integrator-peers"
        )
        self.charm = self.harness.charm

    def test_on_start(self):
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        self.charm.on.start.emit()
        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, BLOCKED_STATUS_NO_CONFIG)

    def test_action_failures(self):
        self.harness.set_leader(True)
        self.harness.update_config({"database-name": None})
        action_event = Mock()
        self.harness.charm._on_get_credentials_action(action_event)

        self.assertEqual(
            action_event.fail.call_args,
            [
                (
                    "The database name, topic name, index name, keyspace name, entity name, or prefix is not specified in the config.",
                )
            ],
        )

        self.harness.update_config({"database-name": "foo"})
        action_event = Mock()
        self.harness.charm._on_get_credentials_action(action_event)

        self.assertEqual(
            action_event.fail.call_args,
            [("The action can be run only after relation is created.",)],
        )

    def test_config_changed(self):
        self.harness.set_leader(True)
        self.harness.update_config({"database-name": "foo"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )
        self.assertEqual(self.harness.charm.config["database-name"], "foo")

        self.harness.update_config({"database-name": "foo1"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )

        self.assertEqual(self.harness.charm.config["database-name"], "foo1")

        self.harness.update_config({"topic-name": "bar"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )
        self.assertEqual(self.harness.charm.config["topic-name"], "bar")

        self.harness.update_config({"entity-type": ENTITY_USER})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )
        self.assertEqual(self.harness.charm.config["entity-type"], ENTITY_USER)

        self.harness.update_config({"extra-user-roles": "admin"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )
        self.assertEqual(self.harness.charm.config["extra-user-roles"], "admin")

        self.harness.update_config({"extra-group-roles": "custom_role_1"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )
        self.assertEqual(self.harness.charm.config["extra-group-roles"], "custom_role_1")

    def test_config_changed_mlflow_not_related(self):
        entity_name = "my-username"
        entity_permissions = '{"my-workspace": "edit"}'
        self.harness.set_leader(True)
        config_changed_event = Mock()

        self.harness.update_config({
            "entity-name": entity_name,
            "entity-permissions": entity_permissions,
        })
        self.harness.charm._on_config_changed(config_changed_event)

        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )
        self.assertEqual(self.harness.charm.config["entity-name"], entity_name)
        self.assertEqual(self.harness.charm.config["entity-permissions"], entity_permissions)
        self.assertEqual(self.harness.charm.entity_name, entity_name)

    def test_action_failure_mlflow_not_related(self):
        entity_name = "my-username"
        entity_permissions = '{"my-workspace": "edit"}'
        self.harness.set_leader(True)
        action_event = Mock()

        self.harness.update_config({
            "entity-name": entity_name,
            "entity-permissions": entity_permissions,
        })
        self.harness.charm._on_get_credentials_action(action_event)

        self.assertEqual(
            action_event.fail.call_args,
            [("The action can be run only after relation is created.",)],
        )

    def test_mlflow_entity_permissions_workspace_map(self):
        workspace_a = "workspace-a"
        workspace_b = "workspace-b"
        grant_a = "admin"
        grant_b = "read-only"

        self.harness.update_config({
            "entity-permissions": f'{{"{workspace_a}": "{grant_a}", "{workspace_b}": "{grant_b}"}}'
        })
        permissions = {
            (p.resource_type, p.resource_name, tuple(p.privileges))
            for p in self.harness.charm.mlflow_entity_permissions
        }

        self.assertEqual(
            permissions,
            {
                ("workspace", workspace_a, (grant_a,)),
                ("workspace", workspace_b, (grant_b,)),
            },
        )

    def test_mlflow_entity_permissions_super_admin(self):
        self.harness.update_config({"entity-permissions": "super-admin"})
        permissions = self.harness.charm.mlflow_entity_permissions
        self.assertEqual(len(permissions), 1)
        self.assertEqual(permissions[0].resource_type, "super-admin")
        self.assertEqual(permissions[0].resource_name, "*")
        self.assertEqual(permissions[0].privileges, [])

    def test_mlflow_entity_permissions_invalid_json(self):
        self.harness.update_config({"entity-permissions": "{not-valid"})
        self.assertEqual(self.harness.charm.mlflow_entity_permissions, [])

    def test_mlflow_entity_permissions_non_mapping(self):
        self.harness.update_config({"entity-permissions": '["a", "b"]'})
        self.assertEqual(self.harness.charm.mlflow_entity_permissions, [])

    def test_mlflow_grants_render_workspace_map(self):
        workspace_a = "workspace-a"
        workspace_b = "workspace-b"
        grant_a = "admin"
        grant_b = "read-only"

        self.harness.update_config({
            "entity-permissions": f'{{"{workspace_b}": "{grant_b}", "{workspace_a}": "{grant_a}"}}'
        })
        rendered = self.harness.charm._render_mlflow_grants(
            self.harness.charm.mlflow_entity_permissions
        )

        self.assertEqual(
            rendered, f'{{"{workspace_a}": "{grant_a}", "{workspace_b}": "{grant_b}"}}'
        )

    def test_mlflow_grants_render_super_admin(self):
        super_admin_grant = "super-admin"

        self.harness.update_config({"entity-permissions": super_admin_grant})
        rendered = self.harness.charm._render_mlflow_grants(
            self.harness.charm.mlflow_entity_permissions
        )

        self.assertEqual(rendered, super_admin_grant)

    def test_get_unit_status(self):
        self.harness.set_leader(True)
        self.harness.update_config({"database-name": "foo"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )
        self.assertEqual(self.harness.charm.config["database-name"], "foo")

        self.rel_id = self.harness.add_relation("mysql", "mysql")
        self.harness.add_relation_unit(self.rel_id, "mysql/0")

        # Simulate sharing the credentials of a new created database.
        self.harness.update_relation_data(
            self.rel_id,
            "mysql",
            {"username": "test-username", "password": "test-password", "database": "foo"},
        )

        self.assertEqual(
            self.harness.model.unit.status,
            ActiveStatus(),
        )

        self.harness.update_config({"database-name": "foo1"})
        self.harness.charm._on_config_changed(Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_REMOVE_DB,
        )

        self.harness.remove_relation(self.rel_id)
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )

        self.harness.update_config({"topic-name": "bar"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(self.harness.charm.config["topic-name"], "bar")
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )

        self.harness.update_config({"topic-name": "*"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(self.harness.charm.config["topic-name"], "*")
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_INVALID_KF_TOPIC,
        )

        self.harness.update_config({"topic-name": "bar"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(self.harness.charm.config["topic-name"], "bar")
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_RELATE,
        )

        self.rel_id = self.harness.add_relation("kafka", "kafka")
        self.harness.add_relation_unit(self.rel_id, "kafka/0")

        # Simulate sharing the credentials of a new created topic.
        self.harness.update_relation_data(
            self.rel_id,
            "kafka",
            {
                "topic": "bar",
                "username": "test-username",
                "password": "test-password",
            },
        )
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            ActiveStatus(),
        )
        self.harness.update_config({"topic-name": "bar1"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BLOCKED_STATUS_REMOVE_KF,
        )

    def test_relation_created(self):
        """Asserts on_database_created is called when the credentials are set in the relation."""
        self.harness.set_leader(True)
        # Set database
        self.harness.update_config({"database-name": "test-database"})
        self.harness.charm._on_config_changed(Mock())

        self.rel_id = self.harness.add_relation("mysql", "database")
        self.harness.add_relation_unit(self.rel_id, "database/0")
        # Simulate sharing the credentials of a new created database.
        self.harness.update_relation_data(
            self.rel_id,
            "database",
            {
                "username": "test-username",
                "password": "test-password",
                "database": "test-database",
            },
        )

        # Test action
        action_event = Mock()
        self.harness.charm._on_get_credentials_action(action_event)
        action_event.set_results.assert_called_once_with({
            "ok": True,
            "mysql": {
                "username": "test-username",
                "password": "test-password",
                "database": "test-database",
            },
        })
