#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import logging
from typing import Dict

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseRequires,
    KafkaRequires,
    TopicCreatedEvent,
)
from ops.charm import ActionEvent, CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

logger = logging.getLogger(__name__)

KAFKA_EXTRA_USER_ROLES = "consumer,producer"


class IntegratorCharm(CharmBase):
    """Integrator charm that connects to database charms."""

    def __init__(self, *args):
        super().__init__(*args)

        self.database = self.model.config.get("database-name", "")
        self.topic = self.model.config.get("topic-name", "")
        self.extra_user_roles = self.model.config.get("extra-user-roles", "")

        self.framework.observe(self.on.get_credentials_action, self._on_get_credentials_action)
        self.framework.observe(self.on.start, self._on_config_changed)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # MySQL
        self.mysql = DatabaseRequires(
            self,
            relation_name="mysql",
            database_name=self.database,
            extra_user_roles=self.extra_user_roles,
        )
        self.framework.observe(self.mysql.on.database_created, self._on_database_created)
        self.framework.observe(self.on["mysql"].relation_broken, self._on_database_relation_broken)

        # PostgreSQL
        self.postgresql = DatabaseRequires(
            self, relation_name="postgresql", database_name=self.database
        )
        self.framework.observe(self.postgresql.on.database_created, self._on_database_created)
        self.framework.observe(
            self.on["postgresql"].relation_broken, self._on_database_relation_broken
        )

        # MongoDB
        self.mongodb = DatabaseRequires(self, relation_name="mongodb", database_name=self.database)
        self.framework.observe(self.mongodb.on.database_created, self._on_database_created)
        self.framework.observe(
            self.on["mongodb"].relation_broken, self._on_database_relation_broken
        )

        kafka_user_roles = KAFKA_EXTRA_USER_ROLES + self.extra_user_roles
        self.kafka = KafkaRequires(
            self, relation_name="kafka", topic=self.topic, extra_user_roles=kafka_user_roles
        )
        self.framework.observe(self.kafka.on.topic_created, self._on_topic_created)
        self.framework.observe(self.on["kafka"].relation_broken, self._on_database_relation_broken)

        self._on_config_changed(None)

    def _on_config_changed(self, event):

        # database
        new_database_name = self.model.config.get("database-name", "")
        new_topic = self.model.config.get("topic-name", "")
        new_extra_user_roles = self.model.config.get("extra-user-roles", "")

        # database name not specified
        if self.database == "":
            self.database == new_database_name
        elif self.database != new_database_name:
            self.unit.status = ActiveStatus(
                f"New database name specified: {new_database_name}. Please remove current relation/s and add a new relation!"
            )
            return

        if self.topic == "":
            self.topic == new_topic
        elif self.topic != new_topic:
            self.unit.status = ActiveStatus(
                f"New database name specified: {new_database_name}. Please remove current relation/s and add a new relation!"
            )
            return

        if self.extra_user_roles == "":
            self.extra_user_roles == new_extra_user_roles
        elif self.extra_user_roles != new_extra_user_roles:
            self.unit.status = ActiveStatus(
                f"New user-extra-roles specified: {new_extra_user_roles}. Please remove current relation/s and add a new relation!"
            )
            return

        # kafka
        self.mysql.database = self.database
        self.postgresql.database = self.database
        self.mongodb.database = self.database
        self.kafka.topic = self.topic

        database_relation_data = {
            "database": self.database,
            "extra-user-roles": self.extra_user_roles,
        }

        self.update_database_relations(database_relation_data)

        # look if kafka is connected
        for rel in self.kafka.relations:
            self.kafka._update_relation_data(
                rel.id,
                {
                    "topic": self.topic,
                    "extra-user-roles": KAFKA_EXTRA_USER_ROLES + self.extra_user_roles,
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
                self.unit.status = ActiveStatus(
                    f"The topic name is specified: {self.topic}. Add relation with Kakfa operator."
                )
        elif self.topic == "":
            if self.is_database_related:
                self.unit.status = ActiveStatus(
                    f"The database name is specified: {self.database}."
                )
            else:
                self.unit.status = ActiveStatus(
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

    def _on_database_relation_broken(self, _):
        """Event triggered when the database relation is removed."""
        if not self.is_database_related:
            self.database = ""

    def _on_kafka_relation_broken(self, _):
        """Event triggered when kafka relatoion is removed."""
        if not self.is_database_related:
            self.kafka = ""

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


if __name__ == "__main__":
    main(IntegratorCharm)
