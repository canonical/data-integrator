# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from unittest.mock import Mock

from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
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
        self.harness.update_config({"database-name": None})
        action_event = Mock()
        self.harness.charm._on_get_credentials_action(action_event)

        self.assertEqual(
            action_event.fail.call_args,
            [("The database name or topic name is not specified in the config.",)],
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
            BlockedStatus(
                "Database: foo, topic: None and extra-user-roles: None. Please add relation with a database or Kafka."
            ),
        )
        self.assertEqual(self.harness.charm.config["database-name"], "foo")
        self.assertEqual(self.harness.charm.mysql.database, "foo")
        self.assertEqual(self.harness.charm.postgresql.database, "foo")
        self.assertEqual(self.harness.charm.mongodb.database, "foo")

        self.harness.update_config({"database-name": "foo1"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus(
                "Database: foo1, topic: None and extra-user-roles: None. Please add relation with a database or Kafka."
            ),
        )

        self.assertEqual(self.harness.charm.config["database-name"], "foo1")
        self.assertEqual(self.harness.charm.mysql.database, "foo1")
        self.assertEqual(self.harness.charm.postgresql.database, "foo1")
        self.assertEqual(self.harness.charm.mongodb.database, "foo1")

        self.harness.update_config({"topic-name": "bar"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus(
                "Database: foo1, topic: bar and extra-user-roles: None. Please add relation with a database or Kafka."
            ),
        )
        self.assertEqual(self.harness.charm.config["topic-name"], "bar")
        self.assertEqual(self.harness.charm.kafka.topic, "bar")

        self.harness.update_config({"extra-user-roles": "admin"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus(
                "Database: foo1, topic: bar and extra-user-roles: admin. Please add relation with a database or Kafka."
            ),
        )
        self.assertEqual(self.harness.charm.config["extra-user-roles"], "admin")
        self.assertEqual(self.harness.charm.kafka.extra_user_roles, "admin")
        self.assertEqual(self.harness.charm.mysql.extra_user_roles, "admin")
        self.assertEqual(self.harness.charm.postgresql.extra_user_roles, "admin")
        self.assertEqual(self.harness.charm.mongodb.extra_user_roles, "admin")

    def test_get_unit_status(self):
        self.harness.set_leader(True)
        self.harness.update_config({"database-name": "foo"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus(
                "Database: foo, topic: None and extra-user-roles: None. Please add relation with a database or Kafka."
            ),
        )
        self.assertEqual(self.harness.charm.config["database-name"], "foo")

        self.rel_id = self.harness.add_relation("mysql", "mysql")
        self.harness.add_relation_unit(self.rel_id, "mysql/0")

        # Simulate sharing the credentials of a new created database.
        self.harness.update_relation_data(
            self.rel_id,
            "mysql",
            {
                "username": "test-username",
                "password": "test-password",
            },
        )

        self.assertEqual(
            self.harness.model.unit.status,
            ActiveStatus("Database: foo, topic: None and extra-user-roles: None."),
        )

        self.harness.update_config({"database-name": "foo1"})
        self.harness.charm._on_config_changed(Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("New database name specified: foo1. Please remove existing relation/s!"),
        )

        self.harness.remove_relation(self.rel_id)
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus(
                "Database: foo1, topic: None and extra-user-roles: None. Please add relation with a database or Kafka."
            ),
        )

        self.harness.update_config({"topic-name": "bar"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(self.harness.charm.config["topic-name"], "bar")
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus(
                "Database: foo1, topic: bar and extra-user-roles: None. Please add relation with a database or Kafka."
            ),
        )

        self.rel_id = self.harness.add_relation("kafka", "kafka")
        self.harness.add_relation_unit(self.rel_id, "kafka/0")

        # Simulate sharing the credentials of a new created topic.
        self.harness.update_relation_data(
            self.rel_id,
            "kafka",
            {
                "username": "test-username",
                "password": "test-password",
            },
        )

        self.assertEqual(
            self.harness.model.unit.status,
            ActiveStatus("Database: foo1, topic: bar and extra-user-roles: None."),
        )
        self.harness.update_config({"topic-name": "bar1"})
        self.harness.charm._on_config_changed(Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("New topic name specified: bar1. Please remove existing relation/s!"),
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
