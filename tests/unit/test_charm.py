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
    "Please specify either topic, index, database name, or prefix",
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
                    "The database name, topic name, index name, or prefix is not specified in the config.",
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
