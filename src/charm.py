#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import base64
import logging
import re
from enum import Enum
from typing import Dict, MutableMapping, Optional, Tuple, Union

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEntityCreatedEvent,
    DatabaseRequires,
    EtcdReadyEvent,
    EtcdRequires,
    IndexCreatedEvent,
    IndexEntityCreatedEvent,
    KafkaRequires,
    OpenSearchRequires,
    RequirerData,
    TopicCreatedEvent,
    TopicEntityCreatedEvent,
)
from ops import (
    ActionEvent,
    ActiveStatus,
    BlockedStatus,
    CharmBase,
    EventBase,
    ModelError,
    Relation,
    RelationBrokenEvent,
    RelationEvent,
    StatusBase,
    main,
)

from literals import DATABASES, ETCD, KAFKA, OPENSEARCH, PEER

logger = logging.getLogger(__name__)

Statuses = Enum("Statuses", ["ACTIVE", "BROKEN", "REMOVED"])
EntityCreatedEvents = Union[
    DatabaseEntityCreatedEvent,
    IndexEntityCreatedEvent,
    TopicEntityCreatedEvent,
]


class IntegratorCharm(CharmBase):
    """Integrator charm that connects to database charms."""

    def _setup_database_requirer(self, relation_name: str) -> DatabaseRequires:
        """Handle the creation of relations and listeners."""
        entity_name, password = self.requested_entities_secret_content
        database_requirer = DatabaseRequires(
            self,
            relation_name=relation_name,
            database_name=self.database_name or "",
            entity_type=self.entity_type or "",
            entity_permissions=self.entity_permissions or "",
            extra_user_roles=self.extra_user_roles or "",
            extra_group_roles=self.extra_group_roles or "",
            requested_entity_name=entity_name,
            requested_entity_password=password,
            external_node_connectivity=True,
        )
        self.framework.observe(
            database_requirer.on.database_created,
            self._on_database_created,
        )
        self.framework.observe(
            database_requirer.on.database_entity_created,
            self._on_entity_created,
        )
        self.framework.observe(self.on[relation_name].relation_broken, self._on_relation_broken)
        return database_requirer

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.get_credentials_action, self._on_get_credentials_action)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on[PEER].relation_changed, self._on_peer_relation_changed)

        self.framework.observe(self.on.update_status, self._on_update_status)

        # Databases: MySQL, PostgreSQL, MongoDB and ZooKeeper
        self.databases: Dict[str, DatabaseRequires] = {
            name: self._setup_database_requirer(name) for name in DATABASES
        }

        # Kafka
        self.kafka = KafkaRequires(
            self,
            relation_name=KAFKA,
            topic=(
                self.topic_name
                if (
                    self.topic_name is not None
                    and KafkaRequires.is_topic_value_acceptable(self.topic_name)
                )
                else ""
            ),
            entity_type=self.entity_type or "",
            entity_permissions=self.entity_permissions or "",
            extra_user_roles=self.extra_user_roles or "",
            extra_group_roles=self.extra_group_roles or "",
            consumer_group_prefix=self.consumer_group_prefix or "",
        )
        self.framework.observe(self.kafka.on.topic_created, self._on_topic_created)
        self.framework.observe(self.kafka.on.topic_entity_created, self._on_entity_created)
        self.framework.observe(self.on[KAFKA].relation_broken, self._on_relation_broken)

        # OpenSearch
        self.opensearch = OpenSearchRequires(
            self,
            relation_name=OPENSEARCH,
            index=self.index_name or "",
            entity_type=self.entity_type or "",
            entity_permissions=self.entity_permissions or "",
            extra_user_roles=self.extra_user_roles or "",
            extra_group_roles=self.extra_group_roles or "",
        )
        self.framework.observe(self.opensearch.on.index_created, self._on_index_created)
        self.framework.observe(self.opensearch.on.index_entity_created, self._on_entity_created)
        self.framework.observe(self.on[OPENSEARCH].relation_broken, self._on_relation_broken)

        # etcd
        if self.model.juju_version.has_secrets:
            self.etcd = EtcdRequires(
                self,
                relation_name=ETCD,
                prefix=self.prefix or "",
                mtls_cert=self.mtls_client_cert,
            )
            self.framework.observe(self.etcd.on.etcd_ready, self._on_etcd_ready)
            self.framework.observe(self.on[ETCD].relation_broken, self._on_relation_broken)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle relation broken event."""
        # update peer databag to trigger the charm status update
        self._update_relation_status(event, Statuses.BROKEN.name)

    def _changes_role_info(self) -> bool:
        """Return whether any of the role config options changed."""
        # Cache values to speed up comparison
        active_type = self.entity_type_active
        active_user_roles = self.extra_user_roles_active
        active_group_roles = self.extra_group_roles_active

        return any([
            active_type and active_type != self.entity_type,
            active_user_roles and active_user_roles != self.extra_user_roles,
            active_group_roles and active_group_roles != self.extra_group_roles,
        ])

    def _get_active_value(self, key: str) -> Optional[str]:
        """Return the active value for a given relation databag key."""
        for requirer in self.databases.values():
            if not requirer.relations:
                continue
            if relation := requirer.relations[0]:
                return requirer.fetch_relation_field(relation.id, key)

        if relation := self.kafka_relation:
            return self.kafka.fetch_relation_field(relation.id, key)
        if relation := self.opensearch_relation:
            return self.opensearch.fetch_relation_field(relation.id, key)
        if relation := self.etcd_relation:
            return self.etcd.fetch_my_relation_field(relation.id, key)

    def get_status(self) -> StatusBase:
        """Return the current application status."""
        if self.model.config.get("requested-entities-secret", None):
            if not self.model.juju_version.has_secrets:
                return BlockedStatus("Cannot use requested-entities-secret without secrets")
            if (entity_name := self.requested_entities_secret_content) and not entity_name[0]:
                return BlockedStatus("Unable to access requested-entities-secret")

        if not any([self.topic_name, self.database_name, self.index_name, self.prefix]):
            return BlockedStatus("Please specify either topic, index, database name, or prefix")

        if self.topic_name and not KafkaRequires.is_topic_value_acceptable(self.topic_name):
            logger.error(
                f"Trying to pass an invalid topic value: {self.topic_name}, please pass an acceptable value instead"
            )
            return BlockedStatus("Please pass an acceptable topic value")

        if not any([
            self.is_database_related,
            self.is_kafka_related,
            self.is_opensearch_related,
            self.is_etcd_related,
        ]):
            return BlockedStatus("Please relate the data-integrator with the desired product")

        if self._changes_role_info():
            return BlockedStatus("To change role info, please remove relation and add it again")

        for mismatch, product_name, name_type, active_name in (
            (
                self.is_kafka_related and self.topic_active != self.topic_name,
                "Kafka",
                "topic",
                self.topic_active,
            ),
            (
                self.is_opensearch_related and self.index_active != self.index_name,
                "OpenSearch",
                "index",
                self.index_active,
            ),
            (
                self.is_etcd_related and self.prefix_active != self.prefix,
                "etcd",
                "prefix",
                self.prefix_active,
            ),
            (
                self.is_database_related
                and any(
                    database != self.database_name for database in self.databases_active.values()
                ),
                "database-name",
                "database name",
                list(self.databases_active.values())[0] if self.databases_active else None,
            ),
        ):
            if mismatch:
                logger.error(
                    f"Trying to change {product_name} configuration for existing relation : To change {name_type}: {active_name}, please remove relation and add it again"
                )
                return BlockedStatus(
                    f"To change {name_type}: {active_name}, please remove relation and add it again"
                )
        return ActiveStatus()

    def _on_update_status(self, _: EventBase) -> None:
        """Handle the status update."""
        self.unit.status = self.get_status()

    def _on_config_changed(self, _: EventBase) -> None:
        """Handle on config changed event."""
        # Only execute in the unit leader
        self.unit.status = self.get_status()

        if not self.unit.is_leader():
            return

        # Update relation databag
        if self.database_name and not self.databases_active:
            self._on_config_changed_database()
        if self.topic_name and not self.topic_active:
            self._on_config_changed_topic()
        if self.index_name and not self.index_active:
            self._on_config_changed_index()
        if self.prefix and (not self.prefix_active or self.mtls_client_cert):
            self._on_config_changed_prefix()

    def _on_config_changed_database(self) -> None:
        """Handle on config changed database event."""
        if self.entity_type:
            database_relation_data = {
                "database": self.database_name,
                "entity-type": self.entity_type,
                "entity-permissions": self.entity_permissions or "",
                "extra-user-roles": self.extra_user_roles or "",
                "extra-group-roles": self.extra_group_roles or "",
            }
        else:
            database_relation_data = {
                "database": self.database_name,
                "extra-user-roles": self.extra_user_roles or "",
            }

        for db_name, rel in self.database_relations.items():
            self.databases[db_name].update_relation_data(rel.id, database_relation_data)

    def _on_config_changed_topic(self) -> None:
        """Handle on config changed topic event."""
        if not KafkaRequires.is_topic_value_acceptable(self.topic_name):
            return

        if self.entity_type:
            topic_relation_data = {
                "topic": self.topic_name,
                "entity-type": self.entity_type,
                "entity-permissions": self.entity_permissions or "",
                "extra-user-roles": self.extra_user_roles or "",
                "extra-group-roles": self.extra_group_roles or "",
            }
        else:
            topic_relation_data = {
                "topic": self.topic_name,
                "extra-user-roles": self.extra_user_roles or "",
                "consumer-group-prefix": self.consumer_group_prefix or "",
            }

        for rel in self.kafka.relations:
            self.kafka.update_relation_data(rel.id, topic_relation_data)

    def _on_config_changed_index(self) -> None:
        """Handle on config changed index event."""
        if self.entity_type:
            index_relation_data = {
                "index": self.index_name,
                "entity-type": self.entity_type,
                "entity-permissions": self.entity_permissions or "",
                "extra-user-roles": self.extra_user_roles or "",
                "extra-group-roles": self.extra_group_roles or "",
            }
        else:
            index_relation_data = {
                "index": self.index_name,
                "extra-user-roles": self.extra_user_roles or "",
            }

        for rel in self.opensearch.relations:
            self.opensearch.update_relation_data(rel.id, index_relation_data)

    def _on_config_changed_prefix(self) -> None:
        """Handle on config changed prefix event."""
        prefix_relation_data = {
            "prefix": self.prefix,
        }

        for rel in self.etcd.relations:
            self.etcd.update_relation_data(rel.id, prefix_relation_data)
            self.etcd.set_mtls_cert(rel.id, self.mtls_client_cert)

    def _on_get_credentials_action(self, event: ActionEvent) -> None:
        """Returns the credentials an action response."""
        if not any([self.database_name, self.topic_name, self.index_name, self.prefix]):
            event.fail(
                "The database name, topic name, index name, or prefix is not specified in the config."
            )
            event.set_results({"ok": False})
            return

        if not any([
            self.is_database_related,
            self.is_kafka_related,
            self.is_opensearch_related,
            self.is_etcd_related,
        ]):
            event.fail("The action can be run only after relation is created.")
            event.set_results({"ok": False})
            return

        result = {"ok": True}

        for name in self.databases_active.keys():
            result[name] = list(self.databases[name].fetch_relation_data().values())[0]

        if self.is_kafka_related:
            result[KAFKA] = list(self.kafka.fetch_relation_data().values())[0]

        if self.is_opensearch_related:
            result[OPENSEARCH] = list(self.opensearch.fetch_relation_data().values())[0]

        if self.is_etcd_related:
            result[ETCD] = {
                "prefix": self.prefix_active,
                "uris": self.etcd.fetch_relation_field(self.etcd_relation.id, "uris"),
                "endpoints": self.etcd.fetch_relation_field(self.etcd_relation.id, "endpoints"),
                "username": self.etcd.fetch_relation_field(self.etcd_relation.id, "username"),
                "tls-ca": self.etcd.fetch_relation_field(self.etcd_relation.id, "tls-ca"),
                "version": self.etcd.fetch_relation_field(self.etcd_relation.id, "version"),
            }

        event.set_results(result)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event triggered when a database was created for this application."""
        logger.debug(f"Database credentials are received: {event.username}")
        self._on_config_changed(event)
        # update values in the databag
        self._update_relation_status(event, Statuses.ACTIVE.name)

    def _on_topic_created(self, event: TopicCreatedEvent) -> None:
        """Event triggered when a topic was created for this application."""
        logger.debug(f"Kafka credentials are received: {event.username}")
        self._on_config_changed(event)
        # update status of the relations in the peer-databag
        self._update_relation_status(event, Statuses.ACTIVE.name)

    def _on_index_created(self, event: IndexCreatedEvent) -> None:
        """Event triggered when an index is created for this application."""
        logger.debug(f"OpenSearch credentials are received: {event.username}")
        self._on_config_changed(event)
        # update status of the relations in the peer-databag
        self._update_relation_status(event, Statuses.ACTIVE.name)

    def _on_entity_created(self, event: EntityCreatedEvents) -> None:
        """Event triggered when an entity is created for this application."""
        logger.debug(f"Entity credentials are received: {event.entity_name}")
        self._on_config_changed(event)
        # update status of the relations in the peer-databag
        self._update_relation_status(event, Statuses.ACTIVE.name)

    def _on_etcd_ready(self, event: EtcdReadyEvent) -> None:
        """Event triggered when the etcd relation is ready."""
        logger.debug("etcd ready received")
        self._on_config_changed(event)
        # update status of the relations in the peer-databag
        self._update_relation_status(event, Statuses.ACTIVE.name)

    def _update_relation_status(self, event: RelationEvent, status: str) -> None:
        """Update the relation status in the peer-relation databag."""
        if not self.unit.is_leader():
            return
        self.set_secret("app", event.relation.name, status)

    def _on_peer_relation_changed(self, _: RelationEvent) -> None:
        """Handle the peer relation changed event."""
        if not self.unit.is_leader():
            return
        removed_relations = []
        # check for relation that has been removed
        for relation_data_key, relation_value in self.app_peer_data.items():
            if relation_value == Statuses.BROKEN.name:
                removed_relations.append(relation_data_key)
        if removed_relations:
            # update the unit status
            self.unit.status = self.get_status()
            # update relation status to removed if relation databag is empty
            for relation_name in removed_relations:
                # check if relation databag is not empty
                if self.model.relations[relation_name]:
                    continue
                self.set_secret("app", relation_name, Statuses.REMOVED.name)

    @property
    def database_name(self) -> Optional[str]:
        """Return the configured database name."""
        return self.model.config.get("database-name", None)

    @property
    def topic_name(self) -> Optional[str]:
        """Return the configured topic name."""
        return self.model.config.get("topic-name", None)

    @property
    def index_name(self) -> Optional[str]:
        """Return the configured database name."""
        return self.model.config.get("index-name", None)

    @property
    def entity_type(self) -> Optional[str]:
        """Return the configured role type."""
        return self.model.config.get("entity-type", None)

    @property
    def entity_permissions(self) -> Optional[str]:
        """Return the configured entity type permissions."""
        return self.model.config.get("entity-permissions", None)

    @property
    def extra_user_roles(self) -> Optional[str]:
        """Return the configured extra user roles."""
        return self.model.config.get("extra-user-roles", None)

    @property
    def extra_group_roles(self) -> Optional[str]:
        """Return the configured extra group roles."""
        return self.model.config.get("extra-group-roles", None)

    @property
    def requested_entities_secret_content(self) -> Tuple[Optional[str], Optional[str]]:
        """Return the configured requested entities secret."""
        try:
            if secret_uri := self.model.config.get("requested-entities-secret", None):
                secret = self.framework.model.get_secret(id=secret_uri)
                content = secret.get_content(refresh=True)
                for key, val in content.items():
                    return key, val
        except ModelError:
            logger.warning("Unable to access requested-entities-secret")
        return None, None

    @property
    def consumer_group_prefix(self) -> Optional[str]:
        """Return the configured consumer group prefix."""
        return self.model.config.get("consumer-group-prefix", None)

    @property
    def mtls_client_cert(self) -> Optional[str]:
        """Return the configured client cert."""
        if not (cert := self.model.config.get("mtls-cert", None)):
            return None

        if re.match(r"(-+(BEGIN|END) [A-Z ]+-+)", cert):
            return cert.replace("\\n", "\n")
        return base64.b64decode(cert).decode("utf-8").strip()

    @property
    def prefix(self) -> Optional[str]:
        """Return the configured prefix."""
        return self.model.config.get("prefix-name", None)

    @property
    def database_relations(self) -> Dict[str, Relation]:
        """Return the active database relations."""
        return {
            name: requirer.relations[0]
            for name, requirer in self.databases.items()
            if len(requirer.relations)
        }

    @property
    def opensearch_relation(self) -> Optional[Relation]:
        """Return the opensearch relation if present."""
        return self.opensearch.relations[0] if len(self.opensearch.relations) else None

    @property
    def kafka_relation(self) -> Optional[Relation]:
        """Return the kafka relation if present."""
        return self.kafka.relations[0] if len(self.kafka.relations) else None

    @property
    def etcd_relation(self) -> Optional[Relation]:
        """Return the etcd relation if present."""
        return (
            self.etcd.relations[0]
            if self.model.juju_version.has_secrets and len(self.etcd.relations)
            else None
        )

    @property
    def databases_active(self) -> Dict[str, str]:
        """Return the configured database name."""
        return {
            name: requirer.fetch_relation_field(requirer.relations[0].id, "database")
            for name, requirer in self.databases.items()
            if requirer.relations
            and requirer.fetch_relation_field(requirer.relations[0].id, "database")
        }

    @property
    def topic_active(self) -> Optional[str]:
        """Return the configured topic name."""
        if relation := self.kafka_relation:
            return self.kafka.fetch_relation_field(relation.id, "topic")

    @property
    def index_active(self) -> Optional[str]:
        """Return the configured index name."""
        if relation := self.opensearch_relation:
            return self.opensearch.fetch_relation_field(relation.id, "index")

    @property
    def prefix_active(self) -> Optional[str]:
        """Return the configured prefix."""
        if relation := self.etcd_relation:
            return self.etcd.fetch_my_relation_field(relation.id, "prefix")

    @property
    def entity_type_active(self) -> Optional[str]:
        """Return the configured entity-type parameter."""
        return self._get_active_value("entity-type")

    @property
    def entity_permissions_active(self) -> Optional[str]:
        """Return the configured entity-permissions parameter."""
        return self._get_active_value("entity-permissions")

    @property
    def extra_user_roles_active(self) -> Optional[str]:
        """Return the configured user-extra-roles parameter."""
        return self._get_active_value("extra-user-roles")

    @property
    def extra_group_roles_active(self) -> Optional[str]:
        """Return the configured group-extra-roles parameter."""
        return self._get_active_value("extra-group-roles")

    @property
    def requested_entities_secret_active(self) -> Optional[str]:
        """Return the configured requested entities secret."""
        return self._get_active_value("requested-entities-secret", None)

    @property
    def is_database_related(self) -> bool:
        """Return if a relation with database is present."""
        possible_relations = [
            self._check_for_credentials(database_requirer)
            for _, database_requirer in self.databases.items()
        ]
        return any(possible_relations)

    @staticmethod
    def _check_for_credentials(requirer: RequirerData) -> bool:
        """Check if credentials are present in the relation databag."""
        for relation in requirer.relations:
            data = requirer.fetch_relation_data(
                [relation.id],
                ["username", "password", "entity-name", "entity-password"],
            ).get(relation.id, {})

            if any([
                all(data.get(field) for field in ("username", "password")),
                all(data.get(field) for field in ("entity-name",)),
            ]):
                return True

        return False

    @property
    def is_kafka_related(self) -> bool:
        """Return if a relation with kafka is present."""
        return self._check_for_credentials(self.kafka)

    @property
    def is_opensearch_related(self) -> bool:
        """Return if a relation with opensearch is present."""
        return self._check_for_credentials(self.opensearch)

    @property
    def is_etcd_related(self) -> bool:
        """Return if a relation with etcd is present."""
        return (
            self.etcd_relation
            and self.etcd.fetch_relation_field(self.etcd_relation.id, "username") is not None
            and self.etcd.fetch_relation_field(self.etcd_relation.id, "uris") is not None
            and self.etcd.fetch_relation_field(self.etcd_relation.id, "endpoints") is not None
            and self.etcd.fetch_relation_field(self.etcd_relation.id, "tls-ca") is not None
            and self.etcd.fetch_relation_field(self.etcd_relation.id, "version") is not None
        )

    @property
    def app_peer_data(self) -> MutableMapping[str, str]:
        """Application peer relation data object."""
        relation = self.model.get_relation(PEER)
        if not relation:
            return {}

        return relation.data[relation.app]

    @property
    def unit_peer_data(self) -> MutableMapping[str, str]:
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
