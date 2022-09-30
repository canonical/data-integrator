#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import logging

from charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseRequires,
)
from ops.charm import ActionEvent, CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

logger = logging.getLogger(__name__)


class IntegratorCharm(CharmBase):
    """Integrator charm that connects to database charms."""

    def __init__(self, *args):
        super().__init__(*args)

        self.database = self.model.config.get("database", "")

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

        self._on_config_changed(None)

    def _on_config_changed(self, event):
        self.database = self.model.config.get("database", "")
        if self.database == "":
            self.unit.status = BlockedStatus("The database name is not specified.")
        elif event:
            self.unit.status = ActiveStatus(f"database: {self.database}")

        self.mysql.database = self.database
        self.postgresql.database = self.database
        self.mongodb.database = self.database

    def _on_get_credentials_action(self, event: ActionEvent) -> None:
        """Returns the credentials an action response."""
        if self.model.config.get("database", "") == "":
            event.fail("The database name is not specified in the config.")
            event.set_results({"ok": False})
            return

        mysql = self.mysql.fetch_relation_data()
        postgresql = self.postgresql.fetch_relation_data()
        mongodb = self.mongodb.fetch_relation_data()

        if not mysql and not postgresql and not mongodb:
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
        event.set_results(result)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event triggered when a database was created for this application."""
        logger.info(f"database credentials are received: {event.username}")
        self.unit.status = ActiveStatus(f"received {self.database} credentials")


if __name__ == "__main__":
    main(IntegratorCharm)
