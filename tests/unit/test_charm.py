# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from unittest.mock import Mock

from ops.model import WaitingStatus
from ops.testing import Harness

from charm import IntegratorCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
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
        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Please provide database or topic name!"),
        )

    def test_action_failures(self):
        self.harness.set_leader(True)
        # self.harness.update_config({"database-name": ""})
        # action_event = Mock()
        # self.harness.charm._on_get_credentials_action(action_event)

        # self.assertEqual(
        #     action_event.fail.call_args,
        #     [("The database name or topic name is not specified in the config.",)],
        # )

        self.harness.update_config({"database-name": "foo"})
        action_event = Mock()
        self.harness.charm._on_get_credentials_action(action_event)

        self.assertEqual(
            action_event.fail.call_args,
            [("The action can be run only after relation is created.",)],
        )

    # def test_config_changed(self):
    #     self.harness.update_config({"database-name": "foo"})
    #     self.harness.charm._on_config_changed(Mock())
    #     self.assertEqual(self.harness.model.unit.status, ActiveStatus("database: foo"))
    #     self.assertEqual(self.harness.charm.config["database-name"], "foo")
    #     self.assertEqual(self.harness.charm.mysql.database, "foo")
    #     self.assertEqual(self.harness.charm.postgresql.database, "foo")
    #     self.assertEqual(self.harness.charm.mongodb.database, "foo")

    #     self.harness.update_config({"database-name": ""})
    #     self.harness.charm._on_config_changed(Mock())
    #     self.assertEqual(
    #         self.harness.model.unit.status, BlockedStatus("The database name is not specified.")
    #     )
    #     self.assertEqual(self.harness.charm.config["database-name"], "")
    #     self.assertEqual(self.harness.charm.mysql.database, "")
    #     self.assertEqual(self.harness.charm.postgresql.database, "")
    #     self.assertEqual(self.harness.charm.mongodb.database, "")

    #     self.harness.update_config({"database-name": "bar"})
    #     self.harness.charm._on_config_changed(Mock())
    #     self.assertEqual(self.harness.model.unit.status, ActiveStatus("database: bar"))
    #     self.assertEqual(self.harness.charm.config["database-name"], "bar")
    #     self.assertEqual(self.harness.charm.mysql.database, "bar")
    #     self.assertEqual(self.harness.charm.postgresql.database, "bar")
    #     self.assertEqual(self.harness.charm.mongodb.database, "bar")

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
        action_event.set_results.assert_called_once_with(
            {
                "ok": True,
                "mysql": {
                    "username": "test-username",
                    "password": "test-password",
                    "database": "test-database",
                },
            }
        )
