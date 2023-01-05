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
            database_name=self.database or "",
            extra_user_roles=self.extra_user_roles or "",
        )
        self.framework.observe(self.mysql.on.database_created, self._on_database_created)
        self.framework.observe(self.on["mysql"].relation_broken, self._on_relation_broken)

        # PostgreSQL
        self.postgresql = DatabaseRequires(
            self,
            relation_name="postgresql",
            database_name=self.database or "",
            extra_user_roles=self.extra_user_roles or "",
        )
        self.framework.observe(self.postgresql.on.database_created, self._on_database_created)
        self.framework.observe(self.on["postgresql"].relation_broken, self._on_relation_broken)

        # MongoDB
        self.mongodb = DatabaseRequires(
            self,
            relation_name="mongodb",
            database_name=self.database or "",
            extra_user_roles=self.extra_user_roles or "",
        )
        self.framework.observe(self.mongodb.on.database_created, self._on_database_created)
        self.framework.observe(self.on["mongodb"].relation_broken, self._on_relation_broken)

        # Kafka
        self.kafka = KafkaRequires(
            self,
            relation_name="kafka",
            topic=self.topic or "",
            extra_user_roles=self.extra_user_roles or "",
        )
        self.framework.observe(self.kafka.on.topic_created, self._on_topic_created)
        self.framework.observe(self.on["kafka"].relation_broken, self._on_relation_broken)

    def _on_relation_broken(self, _):
        """Handle relation broken event."""
        logger.info("On relation broken!")
        logger.info(f"Is database related: {self.is_database_related}")
        logger.info(f"Is Kafka related: {self.is_kafka_related}")
        self._on_config_changed(None)

    def _on_config_changed(self, _):
        """Handle on config changed event."""
        # Only execute in the unit leader
        if not self.unit.is_leader():
            return

        # read new parameters
        new_database_name = self.model.config.get("database-name", None)
        new_topic = self.model.config.get("topic-name", None)
        new_extra_user_roles = self.model.config.get("extra-user-roles", None)

        # get the unit status
        status = self._get_unit_status()

        # if the status is active set new values otherwise return
        if not isinstance(status, ActiveStatus):
            # set status
            self.unit.status = status
            return

        # update parameter in the relation databag
        self.set_secret("app", "database", new_database_name)
        self.set_secret("app", "topic", new_topic)
        self.set_secret("app", "extra-user-roles", new_extra_user_roles)

        self.mysql.database = self.database or ""
        self.postgresql.database = self.database or ""
        self.mongodb.database = self.database or ""
        # Update relation databag
        database_relation_data = {
            "database": self.database,
            "extra-user-roles": self.extra_user_roles or "",
        }
        self.update_database_relations(database_relation_data)

        self.kafka.topic = self.topic or ""
        # Update relation databag
        for rel in self.kafka.relations:
            self.kafka._update_relation_data(
                rel.id,
                {
                    "topic": self.topic,
                    "extra-user-roles": self.extra_user_roles or "",
                },
            )

        # set status
        self.unit.status = status

    def _get_unit_status(self):
        """Return the status based on the configured and new parameters."""
        # read new parameters
        new_database_name = self.model.config.get("database-name", None)
        new_topic = self.model.config.get("topic-name", None)
        new_extra_user_roles = self.model.config.get("extra-user-roles", None)

        if not new_database_name and not new_topic:
            if self.is_database_related or self.is_kafka_related:
                return BlockedStatus(
                    "Remove existing relation and then provide new database or new topic name!"
                )
            else:
                return WaitingStatus("Please provide database or topic name!")

        if new_database_name:
            if new_database_name != self.database:
                if self.is_database_related:
                    return BlockedStatus(
                        f"New database name specified: {new_database_name}. Please remove existing relation/s!"
                    )

        if new_topic:
            if new_topic != self.topic:
                if self.is_kafka_related:
                    return BlockedStatus(
                        f"New topic name specified: {new_topic}. Please remove existing relation/s!."
                    )

        if new_extra_user_roles:
            if new_extra_user_roles != self.extra_user_roles:
                if self.is_kafka_related or self.is_database_related:
                    return BlockedStatus(
                        f"New extra-user-roles specified: {new_extra_user_roles}. Please remove existing relation/s!."
                    )
        extra_msg = ""
        if not self.is_kafka_related and not self.is_database_related:
            extra_msg = " Please add relation!"

        return ActiveStatus(
            f"Database: {new_database_name}, topic: {new_topic} and extra-user-roles: {new_extra_user_roles}.{extra_msg}"
        )

    def update_database_relations(self, database_relation_data: Dict):
        """Update the relation data of the related databases."""
        for rel in self.mysql.relations:
            self.mysql._update_relation_data(rel.id, database_relation_data)
        for rel in self.postgresql.relations:
            self.postgresql._update_relation_data(rel.id, database_relation_data)
        for rel in self.mongodb.relations:
            self.mongodb._update_relation_data(rel.id, database_relation_data)

    def _on_get_credentials_action(self, event: ActionEvent) -> None:
        """Returns the credentials an action response."""
        if self.model.config.get("database-name", None) and self.model.config.get(
            "topic-name", None
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
        self._on_config_changed(None)

    def _on_topic_created(self, event: TopicCreatedEvent) -> None:
        """Event triggered when a topic was created for this application."""
        logger.info(f"Kafka credentials are received: {event.username}")
        self._on_config_changed(None)

    @property
    def database(self):
        """Return the configured database name."""
        return self.get_secret("app", "database")

    @property
    def topic(self):
        """Return the configured topic name."""
        return self.get_secret("app", "topic")

    @property
    def extra_user_roles(self):
        """Return the configured user-extra-roles parameter."""
        return self.get_secret("app", "extra-user-roles")

    @property
    def is_database_related(self):
        """Return if a relation with database is present."""
        possible_relations = [
            self._is_related(self.mysql.relations),
            self._is_related(self.postgresql.relations),
            self._is_related(self.mongodb.relations),
        ]
        logger.info(f"Possible relations: {possible_relations}")
        return any(possible_relations)

    def _is_related(self, relations) -> bool:
        """Check if credentials are present in the relation databag."""
        for r in relations:
            logger.info(f"relation data: {r.data}")
            logger.info(f"relation app: {r.app}")
            logger.info(f"relation app data: {r.data[r.app]}")
            if "username" in r.data[r.app] and "password" in r.data[r.app]:
                return True
        return False

    @property
    def is_kafka_related(self):
        """Return if a relation with kafka is present."""
        return self._is_related(self.kafka.relations)

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
