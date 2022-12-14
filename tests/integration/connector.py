#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import mysql.connector
import psycopg2
from pymongo import MongoClient


class MysqlConnector:
    """Context manager for mysql connector."""

    def __init__(self, config: dict):
        """Initialize the context manager.

        Args:
            config: Configuration dict for the mysql connector, like:
                config = {
                    "user": user,
                    "password": remote_data["password"],
                    "host": host,
                    "database": database,
                    "raise_on_warnings": False,
                }
        """
        self.config = config

    def __enter__(self):
        """Create the connection and return a cursor."""
        self.connection = mysql.connector.connect(**self.config)
        self.cursor = self.connection.cursor()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Handle transaction and connection close."""
        self.connection.commit()
        self.cursor.close()
        self.connection.close()


class PostgreSQLConnector:
    """Context manager for PostrgreSQL connector."""

    def __init__(self, config: str):
        """Initialize the context manager.

        Args:
            config: Connection string for the postgresql connector
        """
        self.config = config

    def __enter__(self):
        """Create the connection and return a cursor."""
        self.connection = psycopg2.connect(self.config)
        self.connection.autocommit = True
        self.cursor = self.connection.cursor()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Handle connection close."""
        self.cursor.close()
        self.connection.close()


class MongoDBConnector:
    """Context manager for PostrgreSQL connector."""

    def __init__(self, config: str):
        """Initialize the context manager.

        Args:
            config: Configuration uri for the mongodb connector
        """
        self.config = config

    def __enter__(self):
        """Create the connection and return a connection."""
        self.connection = MongoClient(
            self.config,
            directConnection=False,
            connect=False,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=2000,
        )

        return self.connection

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Handle connection close."""
        self.connection.close()
