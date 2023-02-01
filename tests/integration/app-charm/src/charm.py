#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import json
import logging

from helpers import (
    KAFKA,
    KAFKA_K8S,
    MONGODB,
    MONGODB_K8S,
    MYSQL,
    MYSQL_K8S,
    POSTGRESQL,
    POSTGRESQL_K8S,
    check_inserted_data_mongodb,
    check_inserted_data_mysql,
    check_inserted_data_postgresql,
    create_table_mongodb,
    create_table_mysql,
    create_table_postgresql,
    create_topic,
    insert_data_mongodb,
    insert_data_mysql,
    insert_data_postgresql,
    produce_messages,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus

logger = logging.getLogger(__name__)


CHARM_KEY = "app"


class ApplicationCharm(CharmBase):
    """Application charm that connects to database charms."""

    def __init__(self, *args):
        super().__init__(*args)
        self.name = CHARM_KEY

        self.framework.observe(getattr(self.on, "start"), self._on_start)
        # these action are needed because hostnames cannot be resolved outside K8s
        self.framework.observe(getattr(self.on, "create_table_action"), self._create_table)
        self.framework.observe(getattr(self.on, "insert_data_action"), self._insert_data)
        self.framework.observe(
            getattr(self.on, "check_inserted_data_action"), self._check_inserted_data
        )

        self.framework.observe(getattr(self.on, "produce_messages_action"), self._produce_messages)
        self.framework.observe(getattr(self.on, "create_topic_action"), self._create_topic)

    def _on_start(self, _) -> None:
        self.unit.status = ActiveStatus()

    def _create_table(self, event) -> None:
        """Handle the action that creates a table on different databases."""
        if not self.unit.is_leader():
            event.fail("The action can be run only on leader unit.")
            return
        # read parameters from the event
        product = event.params["product"]
        database_name = event.params["database-name"]
        credentials = json.loads(event.params["credentials"])

        if product == POSTGRESQL or product == POSTGRESQL_K8S:
            create_table_postgresql(credentials, database_name)
        elif product == MYSQL or product == MYSQL_K8S:
            create_table_mysql(credentials, database_name)
        elif product == MONGODB or product == MONGODB_K8S:
            create_table_mongodb(credentials, database_name)
        else:
            raise ValueError()

    def _insert_data(self, event) -> None:
        """Handle the action that insert some data on different databases."""
        if not self.unit.is_leader():
            event.fail("The action can be run only on leader unit.")
            return
        # read parameters from the event
        product = event.params["product"]
        database_name = event.params["database-name"]
        credentials = json.loads(event.params["credentials"])

        if product == POSTGRESQL or product == POSTGRESQL_K8S:
            insert_data_postgresql(credentials, database_name)
        elif product == MYSQL or product == MYSQL_K8S:
            insert_data_mysql(credentials, database_name)
        elif product == MONGODB or product == MONGODB_K8S:
            insert_data_mongodb(credentials, database_name)
        else:
            raise ValueError()

    def _check_inserted_data(self, event) -> None:
        """Handle the action that checks if data are written on different databases."""
        if not self.unit.is_leader():
            event.fail("The action can be run only on leader unit.")
            return
        # read parameters from the event
        product = event.params["product"]
        database_name = event.params["database-name"]
        credentials = json.loads(event.params["credentials"])

        if product == POSTGRESQL or product == POSTGRESQL_K8S:
            check_inserted_data_postgresql(credentials, database_name)
        elif product == MYSQL or product == MYSQL_K8S:
            check_inserted_data_mysql(credentials, database_name)
        elif product == MONGODB or product == MONGODB_K8S:
            check_inserted_data_mongodb(credentials, database_name)
        else:
            raise ValueError()

    def _produce_messages(self, event) -> None:
        """Handle the action that checks if data are written on different databases."""
        if not self.unit.is_leader():
            event.fail("The action can be run only on leader unit.")
            return
        # read parameters from the event
        product = event.params["product"]
        topic_name = event.params["topic-name"]
        credentials = json.loads(event.params["credentials"])

        if product == KAFKA or product == KAFKA_K8S:
            produce_messages(credentials, topic_name)
        else:
            raise ValueError()

    def _create_topic(self, event) -> None:
        """Handle the action that checks if data are written on different databases."""
        if not self.unit.is_leader():
            event.fail("The action can be run only on leader unit.")
            return
        # read parameters from the event
        product = event.params["product"]
        topic_name = event.params["topic-name"]
        credentials = json.loads(event.params["credentials"])

        if product == KAFKA or product == KAFKA_K8S:
            create_topic(credentials, topic_name)
        else:
            raise ValueError()


if __name__ == "__main__":
    main(ApplicationCharm)
