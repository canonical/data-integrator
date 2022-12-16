#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import logging
from typing import Dict, Optional

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseRequires,
    KafkaRequires,
    TopicCreatedEvent,
)
from ops.charm import ActionEvent, CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

logger = logging.getLogger(__name__)

PEER = "data-integrator-peers"


class IntegratorCharm(CharmBase):
    """Integrator charm that connects to database charms."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.get_credentials_action, self._on_get_credentials_action)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # MySQL
        self.mysql = DatabaseRequires(
            self,
            relation_name="mysql",
            database_name=self.database,
            extra_user_roles=self.extra_user_roles,
        )
        self.framework.observe(self.mysql.on.database_created, self._on_database_created)

        # PostgreSQL
        self.postgresql = DatabaseRequires(
            self, relation_name="postgresql", database_name=self.database
        )
        self.framework.observe(self.postgresql.on.database_created, self._on_database_created)

        # MongoDB
        self.mongodb = DatabaseRequires(self, relation_name="mongodb", database_name=self.database)
        self.framework.observe(self.mongodb.on.database_created, self._on_database_created)

        self.kafka = KafkaRequires(
            self, relation_name="kafka", topic=self.topic, extra_user_roles=self.extra_user_roles
        )
        self.framework.observe(self.kafka.on.topic_created, self._on_topic_created)

    def _on_config_changed(self, event):
        """Handle on config changed event."""
        # Read new parameters
        new_database_name = self.model.config.get("database-name", "")
        new_topic = self.model.config.get("topic-name", "")
        new_extra_user_roles = self.model.config.get("extra-user-roles", "")

        # check the
        if self.database == "" or not self.is_database_related:
            self.set_secret("app", "database", new_database_name)
        elif self.database != new_database_name:
            self.unit.status = WaitingStatus(
                f"New database name specified: {new_database_name}. Please remove current relation/s and add a new relation!"
            )
            self.set_secret("app", "database", new_database_name)
            return

        if self.topic == "" or not self.is_kafka_related:
            self.set_secret("app", "topic", new_topic)
        elif self.topic != new_topic:
            self.unit.status = WaitingStatus(
                f"New database name specified: {new_database_name}. Please remove current relation/s and add a new relation!"
            )
            self.set_secret("app", "topic", new_topic)
            return

        if self.extra_user_roles == "":
            self.set_secret("app", "extra-user-roles", new_extra_user_roles)
        elif self.extra_user_roles != new_extra_user_roles:
            self.unit.status = BlockedStatus(
                f"New user-extra-roles specified: {new_extra_user_roles}. Please remove current relation/s and add a new relation!"
            )
            self.set_secret("app", "extra-user-roles", new_extra_user_roles)
            return

        # kafka
        self.mysql.database = self.get_secret("app", "database")
        self.postgresql.database = self.get_secret("app", "database")
        self.mongodb.database = self.get_secret("app", "database")
        self.kafka.topic = self.get_secret("app", "topic")

        database_relation_data = {
            "database": self.get_secret("app", "database"),
            "extra-user-roles": self.get_secret("app", "extra-user-roles"),
        }

        self.update_database_relations(database_relation_data)

        # look if kafka is connected
        for rel in self.kafka.relations:
            self.kafka._update_relation_data(
                rel.id,
                {
                    "topic": self.topic,
                    "extra-user-roles": self.extra_user_roles
                    + self.get_secret("app", "extra-user-roles"),
                },
            )

        # output the correct message.
        self.set_status(event)

    def update_database_relations(self, database_relation_data: Dict):
        """Update the relation data of the related databases."""
        for rel in self.mysql.relations:
            self.mysql._update_relation_data(rel.id, database_relation_data)
        for rel in self.postgresql.relations:
            self.postgresql._update_relation_data(rel.id, database_relation_data)
        for rel in self.mongodb.relations:
            self.mongodb._update_relation_data(rel.id, database_relation_data)

    def set_status(self, event):
        """Set the unit status."""
        if self.database == "" and self.topic == "":
            self.unit.status = BlockedStatus("The database name or topic name is not specified.")
        elif self.database == "":
            if self.is_kafka_related:
                self.unit.status = ActiveStatus(f"The topic name is specified: {self.topic}.")
            else:
                self.unit.status = WaitingStatus(
                    f"The topic name is specified: {self.topic}. Add relation with Kakfa operator."
                )
        elif self.topic == "":
            if self.is_database_related:
                self.unit.status = ActiveStatus(
                    f"The database name is specified: {self.database}."
                )
            else:
                self.unit.status = WaitingStatus(
                    f"The database name is specified: {self.database}. Add relation with a database."
                )

        elif event:
            self.unit.status = ActiveStatus(
                f"Both database name({self.database}) and topic name({self.topic}) has been specified!"
            )

    def _on_get_credentials_action(self, event: ActionEvent) -> None:
        """Returns the credentials an action response."""
        if (
            self.model.config.get("database-name", "") == ""
            and self.model.config.get("topic-name", "") == ""
        ):
            event.fail("The database name or topic name is not specified in the config.")
            event.set_results({"ok": False})
            return

        mysql = self.mysql.fetch_relation_data()
        postgresql = self.postgresql.fetch_relation_data()
        mongodb = self.mongodb.fetch_relation_data()
        kafka = self.kafka.fetch_relation_data()

        if not mysql and not postgresql and not mongodb and not kafka:
            event.fail("The action can be run only after relation is created.")
            event.set_results({"ok": False})
            return

        result = {"ok": True}
        if mysql:
            result["mysql"] = list(mysql.values())[0]
        if postgresql:
            result["postgresql"] = list(postgresql.values())[0]
        if mongodb:
            result["mongodb"] = list(mongodb.values())[0]
        if kafka:
            result["kafka"] = list(kafka.values())[0]
        event.set_results(result)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event triggered when a database was created for this application."""
        logger.info(f"database credentials are received: {event.username}")
        self.unit.status = ActiveStatus(f"Received credentials for database: {self.database}.")

    def _on_topic_created(self, event: TopicCreatedEvent) -> None:
        """Event triggered when a topic was created for this application."""
        logger.info(f"Topic credentials are received: {event.username}")
        self.unit.status = ActiveStatus(f"Received credentials for topic: {self.topic}")

    @property
    def database(self):
        """Return the configured database name."""
        return self.get_secret("app", "database") if self.get_secret("app", "database") else ""

    @property
    def topic(self):
        """Return the configured topic name."""
        return self.get_secret("app", "topic") if self.get_secret("app", "topic") else ""

    @property
    def extra_user_roles(self):
        """Return the configured user-extra-roles parameter."""
        return (
            self.get_secret("app", "extra-user-roles")
            if self.get_secret("app", "extra-user-roles")
            else ""
        )

    @property
    def is_database_related(self):
        """Return if a relation with database is present."""
        if self.mysql.relations:
            return True
        if self.postgresql.relations:
            return True
        if self.mongodb.relations:
            return True
        # no reltation with databases
        return False

    @property
    def is_kafka_related(self):
        """Return if a relation with kafka is present."""
        if self.kafka.relations:
            return True
        # no reltation with kafka
        return False

    @property
    def app_peer_data(self) -> Dict:
        """Application peer relation data object."""
        relation = self.model.get_relation(PEER)
        if not relation:
            return {}

        return relation.data[self.app]

    @property
    def unit_peer_data(self) -> Dict:
        """Peer relation data object."""
        relation = self.model.get_relation(PEER)
        if relation is None:
            return {}

        return relation.data[self.unit]

    def get_secret(self, scope: str, key: str) -> Optional[str]:
        """Get secret from the secret storage."""
        if scope == "unit":
            return self.unit_peer_data.get(key, None)
        elif scope == "app":
            return self.app_peer_data.get(key, None)
        else:
            raise RuntimeError("Unknown secret scope.")

    def set_secret(self, scope: str, key: str, value: Optional[str]) -> None:
        """Set secret in the secret storage."""
        if scope == "unit":
            if not value:
                del self.unit_peer_data[key]
                return
            self.unit_peer_data.update({key: value})
        elif scope == "app":
            if not value:
                del self.app_peer_data[key]
                return
            self.app_peer_data.update({key: value})
        else:
            raise RuntimeError("Unknown secret scope.")


if __name__ == "__main__":
    main(IntegratorCharm)
