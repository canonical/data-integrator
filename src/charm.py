#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import logging

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

KAFKA_EXTRA_USER_ROLES = "consumer,producer,admin"


class IntegratorCharm(CharmBase):
    """Integrator charm that connects to database charms."""

    def __init__(self, *args):
        super().__init__(*args)

        self.database = self.model.config.get("database-name", "")
        self.topic = self.model.config.get("topic-name", "")


        self.framework.observe(self.on.get_credentials_action, self._on_get_credentials_action)
        self.framework.observe(self.on.start, self._on_config_changed)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # MySQL
        self.mysql = DatabaseRequires(self, relation_name="mysql", database_name=self.database)
        self.framework.observe(self.mysql.on.database_created, self._on_database_created)

        # PostgreSQL
        self.postgresql = DatabaseRequires(
            self, relation_name="postgresql", database_name=self.database
        )
        self.framework.observe(self.postgresql.on.database_created, self._on_database_created)

        # MongoDB
        self.mongodb = DatabaseRequires(self, relation_name="mongodb", database_name=self.database)
        self.framework.observe(self.mongodb.on.database_created, self._on_database_created)

        self.kafka = KafkaRequires(self, relation_name="kafka", topic_name=self.topic, extra_user_roles=KAFKA_EXTRA_USER_ROLES)
        self.framework.observe(self.kafka.on.topic_created, self._on_topic_created)

        self._on_config_changed(None)

    def _on_config_changed(self, event):
        
        # database
        self.database = self.model.config.get("database-name", "")
        # kafka
        self.topic = self.model.config.get("topic-name", "")
        

        self.mysql.database = self.database
        self.postgresql.database = self.database
        self.mongodb.database = self.database
        self.kafka.topic = self.topic

        # look if database is related
        is_database_related = False

        for rel in self.mysql.relations:
            self.mysql._update_relation_data(rel.id, {"database": self.database})
            is_database_related = True
        for rel in self.postgresql.relations:
            self.postgresql._update_relation_data(rel.id, {"database": self.database})
            is_database_related = True
        for rel in self.mongodb.relations:
            self.mongodb._update_relation_data(rel.id, {"database": self.database})
            is_database_related = True

        # look if kafka is connected          
        is_kafka_related = False
        for rel in self.mongodb.relations:
            self.kafka._update_relation_data(rel.id, {"topic": self.topic, "extra-user-roles": KAFKA_EXTRA_USER_ROLES})
            is_kafka_related = True

        
        # output the correct message.

        if self.database == "" and self.topic == "":
            self.unit.status = BlockedStatus("The database name or topic name is not specified.")
        elif self.database == "":
            if is_kafka_related:
                self.unit.status = ActiveStatus(f"The topic name is specified: {self.topic}.")
            else:
                self.unit.status = ActiveStatus(f"The topic name is specified: {self.topic}. Add relation with Kakfa operator.")
        elif self.topic == "":
            if is_database_related:
                self.unit.status = ActiveStatus(f"The database name is specified: {self.topic}.")
            else:
                self.unit.status = ActiveStatus(f"The database name is specified: {self.topic}. Add relation with a database.")

        elif event:
            self.unit.status = ActiveStatus(f"Both database name({self.database}) and topic name({self.topic}) has been specified!")

    def _on_get_credentials_action(self, event: ActionEvent) -> None:
        """Returns the credentials an action response."""
        if self.model.config.get("database-name", "") == "" and self.model.config.get("topic-name", "") == "":
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


if __name__ == "__main__":
    main(IntegratorCharm)
