#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from json import JSONDecodeError
from pathlib import Path
from ssl import CERT_NONE, PROTOCOL_TLS_CLIENT, SSLContext
from typing import Dict, Generator

import psycopg2
import requests
from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import (
    EXEC_PROFILE_DEFAULT,
    Cluster,
    ExecutionProfile,
    Session,
)
from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy
from charms.kafka.v0.client import KafkaClient
from charms.tls_certificates_interface.v4.tls_certificates import (
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_private_key,
)
from connector import MysqlConnector, get_zookeeper_client
from kafka.admin import NewTopic
from pymongo import MongoClient
from spark_test.core.kyuubi import KyuubiClient

MYSQL = "mysql"
MYSQL_ROUTER = "mysql-router"
POSTGRESQL = "postgresql"
PGBOUNCER = "pgbouncer"
MONGODB = "mongodb"
OPENSEARCH = "opensearch"

MYSQL_K8S = "mysql-k8s"
MYSQL_ROUTER_K8S = "mysql-router-k8s"
POSTGRESQL_K8S = "postgresql-k8s"
PGBOUNCER_K8S = "pgbouncer-k8s"
MONGODB_K8S = "mongodb-k8s"

DATABASE_NAME = "test_database"
KAFKA = "kafka"
ZOOKEEPER = "zookeeper"

KAFKA_K8S = "kafka-k8s"
ZOOKEEPER_K8S = "zookeeper-k8s"

KYUUBI = "kyuubi"
ETCD = "etcd"
TABLE_SCHEMA = [("name", str), ("score", int)]
ETCD_SNAP_DIR = "/var/snap/charmed-etcd/common"
ETCD_CERTS_DIR = f"{ETCD_SNAP_DIR}/certificates"

CASSANDRA = "cassandra"

TABLE_NAME = "test_table"


def build_postgresql_connection_string(credentials: Dict[str, str], database_name) -> str:
    """Generate the connection string for PostgreSQL from relation data."""
    username = credentials[POSTGRESQL]["username"]
    password = credentials[POSTGRESQL]["password"]
    endpoints = credentials[POSTGRESQL]["endpoints"]
    host, port = endpoints.split(",")[0].split(":")
    # Build the complete connection string to connect to the database.
    return f"dbname='{database_name}' user='{username}' host='{host}' port='{port}' password='{password}' connect_timeout=10"


def check_inserted_data_postgresql(credentials: Dict[str, str], database_name: str) -> bool:
    """Check that data are inserted in a table for Postgresql."""
    connection_string = build_postgresql_connection_string(credentials, database_name)
    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        # Read data from previously created database.
        try:
            cursor.execute(f"SELECT data FROM {TABLE_NAME};")
            data = cursor.fetchone()
            assert data[0] == "some data"
        except Exception:
            return False
        return True


def create_table_postgresql(credentials: Dict[str, str], database_name: str) -> bool:
    """Create a table in a Postgresql database."""
    connection_string = build_postgresql_connection_string(credentials, database_name)
    # test connection for PostgreSQL with retrieved credentials
    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        # Check that it's possible to write and read data from the database that
        # was created for the application.
        try:
            connection.autocommit = True
            cursor.execute(f"DROP TABLE IF EXISTS {TABLE_NAME};")
            cursor.execute(f"CREATE TABLE {TABLE_NAME}(data TEXT);")
            cursor.execute(f"INSERT INTO {TABLE_NAME}(data) VALUES('some data');")
            cursor.execute(f"SELECT data FROM {TABLE_NAME};")
            data = cursor.fetchone()
            assert data[0] == "some data"
        except Exception:
            return False
        return True


def insert_data_postgresql(credentials: Dict[str, str], database_name: str) -> bool:
    """Insert some testing data in a Postgresql database."""
    connection_string = build_postgresql_connection_string(credentials, database_name)
    # test connection for PostgreSQL with retrieved credentials
    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        # Check that it's possible to read data from the database that
        # was created for the application.
        try:
            connection.autocommit = True
            cursor.execute(f"INSERT INTO {TABLE_NAME}(data) VALUES('some data');")
            cursor.execute(f"SELECT data FROM {TABLE_NAME};")
        except Exception:
            return False
        return True


# MYSQL


def get_mysql_config(credentials: Dict[str, str], database_name) -> Dict[str, str]:
    """Create the configuration params need to connect with MySQL."""
    config = {
        "user": credentials[MYSQL]["username"],
        "password": credentials[MYSQL]["password"],
        "host": credentials[MYSQL]["endpoints"].split(":")[0],
        "port": credentials[MYSQL]["endpoints"].split(":")[1],
        "database": database_name,
        "raise_on_warnings": False,
    }
    return config


def check_inserted_data_mysql(credentials: Dict[str, str], database_name: str) -> bool:
    """Check that data are inserted in a table for MySQL."""
    config = get_mysql_config(credentials, database_name)
    with MysqlConnector(config) as cursor:
        try:
            cursor.execute(
                f"SELECT * FROM {TABLE_NAME} where username = '{credentials[MYSQL]['username']}'"
            )
            rows = cursor.fetchall()
            first_row = rows[0]
            # username, password, endpoints, version, ro-endpoints
            assert first_row[1] == credentials[MYSQL]["username"]
            assert first_row[2] == credentials[MYSQL]["password"]
            assert first_row[3] == credentials[MYSQL]["endpoints"]
            assert first_row[4] == credentials[MYSQL]["version"]
            assert first_row[5] == credentials[MYSQL]["read-only-endpoints"]
        except Exception:
            return False
        return True


def create_table_mysql(credentials: Dict[str, str], database_name: str) -> bool:
    """Create a table in a MySQL database."""
    config = get_mysql_config(credentials, database_name)
    with MysqlConnector(config) as cursor:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {TABLE_NAME};")
            cursor.execute(
                (
                    f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} ("
                    "id SMALLINT not null auto_increment,"
                    "username VARCHAR(255),"
                    "password VARCHAR(255),"
                    "endpoints VARCHAR(255),"
                    "version VARCHAR(255),"
                    "read_only_endpoints VARCHAR(255),"
                    "PRIMARY KEY (id))"
                )
            )
        except Exception:
            return False
        return True


def insert_data_mysql(credentials: Dict[str, str], database_name: str) -> bool:
    """Insert some testing data in a MySQL database."""
    config = get_mysql_config(credentials, database_name)
    with MysqlConnector(config) as cursor:
        try:
            cursor.execute(
                " ".join((
                    f"INSERT INTO {TABLE_NAME} (",
                    "username, password, endpoints, version, read_only_endpoints)",
                    "VALUES (%s, %s, %s, %s, %s)",
                )),
                (
                    credentials[MYSQL]["username"],
                    credentials[MYSQL]["password"],
                    credentials[MYSQL]["endpoints"],
                    credentials[MYSQL]["version"],
                    credentials[MYSQL]["read-only-endpoints"],
                ),
            )
        except Exception:
            return False
        return True


# MONGODB


def check_inserted_data_mongodb(credentials: Dict[str, str], database_name: str) -> bool:
    """Check that data are inserted in a table for MongoDB."""
    connection_string = credentials[MONGODB]["uris"]
    try:
        client = MongoClient(
            connection_string,
            directConnection=False,
            connect=False,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=2000,
        )

        # test some operations
        db = client[database_name]
        test_collection = db[TABLE_NAME]
        query = test_collection.find({}, {"release_name": 1})
        assert query[0]["release_name"] == "Focal Fossa"
        client.close()
    except Exception:
        return False
    return True


def create_table_mongodb(credentials: Dict[str, str], database_name: str) -> bool:
    """Create a table in a MongoDB database."""
    connection_string = credentials[MONGODB]["uris"]
    try:
        client = MongoClient(
            connection_string,
            directConnection=False,
            connect=False,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=2000,
        )

        # test some operations
        db = client[database_name]
        test_collection = db[TABLE_NAME]
        test_collection.find_one()
        client.close()
    except Exception:
        return False
    return True


def insert_data_mongodb(credentials: Dict[str, str], database_name: str) -> bool:
    """Insert some testing data in a MongoDB collection."""
    connection_string = credentials[MONGODB]["uris"]
    try:
        client = MongoClient(
            connection_string,
            directConnection=False,
            connect=False,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=2000,
        )

        # test some operations
        db = client[database_name]
        test_collection = db[TABLE_NAME]
        ubuntu = {"release_name": "Focal Fossa", "version": 20.04, "LTS": True}
        test_collection.insert_one(ubuntu)
        client.close()
    except Exception:
        return False
    return True


# KAFKA


def produce_messages(credentials: Dict[str, str], topic_name: str):
    """Produce message to a topic."""
    username = credentials[KAFKA]["username"]
    password = credentials[KAFKA]["password"]
    servers = credentials[KAFKA]["endpoints"].split(",")
    security_protocol = "SASL_PLAINTEXT"

    if not (username and password and servers):
        raise KeyError("missing relation data from app charm")

    client = KafkaClient(
        servers=servers,
        username=username,
        password=password,
        security_protocol=security_protocol,
    )
    for n in range(0, 5):
        client.produce_message(topic_name=topic_name, message_content=f"Test message #{n}")


def create_topic(credentials: Dict[str, str], topic_name: str):
    """Produce message to a topic."""
    username = credentials[KAFKA]["username"]
    password = credentials[KAFKA]["password"]
    servers = credentials[KAFKA]["endpoints"].split(",")
    security_protocol = "SASL_PLAINTEXT"

    if not (username and password and servers):
        raise KeyError("missing relation data from app charm")

    client = KafkaClient(
        servers=servers,
        username=username,
        password=password,
        security_protocol=security_protocol,
    )

    topic = NewTopic(
        name=topic_name,
        num_partitions=5,
        replication_factor=1,
    )
    client.create_topic(topic)


# OPENSEARCH


def http_request(
    credentials: Dict[str, str], endpoint: str, method: str, payload: str
) -> Dict[str, any]:
    """Produce message to a topic."""
    username = credentials["username"]
    password = credentials["password"]
    servers = credentials["endpoints"].split(",")

    if not (username and password and servers):
        raise KeyError("missing relation data from app charm")

    if endpoint.startswith("/"):
        endpoint = endpoint[1:]

    full_url = f"https://{servers[0]}/{endpoint}"

    with requests.Session() as s, tempfile.NamedTemporaryFile(mode="w+") as chain:
        chain.write(credentials.get("tls-ca"))
        chain.seek(0)
        request_kwargs = {
            "verify": chain.name,
            "method": method.upper(),
            "url": full_url,
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
        }
        if payload:
            request_kwargs["data"] = payload

        s.auth = (username, password)
        resp = s.request(**request_kwargs)
    try:
        return resp.json()
    except JSONDecodeError:
        return {"status_code": resp.status_code, "text": resp.text}


# ZOOKEEPER


def create_table_zookeeper(credentials: Dict[str, str], database_name: str) -> bool:
    """Create a zNode in a ZooKeeper database."""
    username = credentials[ZOOKEEPER]["username"]
    password = credentials[ZOOKEEPER]["password"]
    servers = credentials[ZOOKEEPER]["endpoints"].split(",")

    port = 2181 if credentials[ZOOKEEPER]["tls"] == "disabled" else 2182

    endpoints = [f"{server}:{port}" for server in servers]
    try:
        with get_zookeeper_client(hosts=endpoints, username=username, password=password) as client:
            client.create(f"/{database_name}/{TABLE_NAME}")

    except Exception:
        return False
    return True


def insert_data_zookeeper(credentials: Dict[str, str], database_name: str) -> bool:
    """Insert some testing data in a ZooKeeper zNode."""
    username = credentials[ZOOKEEPER]["username"]
    password = credentials[ZOOKEEPER]["password"]
    servers = credentials[ZOOKEEPER]["endpoints"].split(",")

    port = 2181 if credentials[ZOOKEEPER]["tls"] == "disabled" else 2182

    endpoints = [f"{server}:{port}" for server in servers]
    try:
        with get_zookeeper_client(hosts=endpoints, username=username, password=password) as client:
            client.set(f"{database_name}/{TABLE_NAME}", "some data".encode("utf-8"))
    except Exception:
        return False
    return True


def check_inserted_data_zookeeper(credentials: Dict[str, str], database_name: str) -> bool:
    """Check that data are inserted in a ZooKeeper zNode."""
    username = credentials[ZOOKEEPER]["username"]
    password = credentials[ZOOKEEPER]["password"]
    servers = credentials[ZOOKEEPER]["endpoints"].split(",")

    port = 2181 if credentials[ZOOKEEPER]["tls"] == "disabled" else 2182

    endpoints = [f"{server}:{port}" for server in servers]
    try:
        with get_zookeeper_client(hosts=endpoints, username=username, password=password) as client:
            data = client.get(f"{database_name}/{TABLE_NAME}")
            assert data.decode("utf-8") == "some data"
    except Exception:
        return False
    return True


# Kyuubi


def create_table_kyuubi(credentials: Dict[str, str], database_name: str) -> bool:
    """Create a table in a Kyuubi backed data warehouse."""
    username = credentials[KYUUBI]["username"]
    password = credentials[KYUUBI]["password"]
    endpoint = credentials[KYUUBI]["endpoints"]
    host, port = endpoint.split(":")

    try:
        client = KyuubiClient(username=username, password=password, host=host, port=port)
        database = client.get_database(database_name)
        database.create_table(TABLE_NAME, TABLE_SCHEMA)
        return TABLE_NAME in database.tables
    except Exception:
        return False


def insert_data_kyuubi(credentials: Dict[str, str], database_name: str) -> bool:
    """Insert some testing data in a Kyuubi backed data warehouse."""
    username = credentials[KYUUBI]["username"]
    password = credentials[KYUUBI]["password"]
    endpoint = credentials[KYUUBI]["endpoints"]
    host, port = endpoint.split(":")

    try:
        client = KyuubiClient(username=username, password=password, host=host, port=port)
        database = client.get_database(database_name)
        table = database.get_table(TABLE_NAME)
        table.insert(("foo", 1), ("bar", 2))
        assert ("foo", 1) in table.rows
        return True
    except Exception:
        return False


def check_inserted_data_kyuubi(credentials: Dict[str, str], database_name: str) -> bool:
    """Check that data are inserted in a ZooKeeper zNode."""
    username = credentials[KYUUBI]["username"]
    password = credentials[KYUUBI]["password"]
    endpoint = credentials[KYUUBI]["endpoints"]
    host, port = endpoint.split(":")

    try:
        client = KyuubiClient(username=username, password=password, host=host, port=port)
        database = client.get_database(database_name)
        table = database.get_table(TABLE_NAME)
        assert ("foo", 1) in table.rows
        assert ("bar", 2) in table.rows
        return True
    except Exception:
        return False


# ETCD


def generate_cert(common_name: str) -> str:
    """Generate a self-signed certificate and private key for testing."""
    ca_private_key = generate_private_key()
    ca_cert = generate_ca(
        private_key=ca_private_key, validity=timedelta(days=365), common_name="ca_common_name"
    )

    client_private_key = generate_private_key()
    client_csr = generate_csr(private_key=client_private_key, common_name=common_name)
    client_cert = generate_certificate(
        client_csr, ca_cert, ca_private_key, validity=timedelta(days=365)
    )
    return "\n".join([client_cert.raw, ca_cert.raw]), client_private_key.raw


def insert_data_etcd(credentials: Dict[str, str], database_name: str) -> bool:
    """Insert some testing data in a Etcd database."""
    uris = credentials["uris"]
    server_ca_cert = credentials["tls-ca"]
    if (
        not Path(Path(ETCD_CERTS_DIR) / "client.pem").exists()
        or not Path(Path(ETCD_CERTS_DIR) / "client.key").exists()
    ):
        raise FileNotFoundError("Missing client certificate or key")
    Path(Path(ETCD_CERTS_DIR) / "ca.pem").write_text(server_ca_cert)

    try:
        output = subprocess.check_output([
            "charmed-etcd.etcdctl",
            "--endpoints",
            uris,
            "--cert",
            f"{ETCD_CERTS_DIR}/client.pem",
            "--key",
            f"{ETCD_CERTS_DIR}/client.key",
            "--cacert",
            f"{ETCD_CERTS_DIR}/ca.pem",
            "put",
            f"{database_name}/foo",
            "bar",
        ])
    except subprocess.CalledProcessError:
        return False
    return output.decode().strip() == "OK"


def check_inserted_data_etcd(credentials: Dict[str, str], database_name: str) -> bool:
    """Check that data are inserted in a Etcd database."""
    uris = credentials["uris"]
    server_ca_cert = credentials["tls-ca"]
    if (
        not Path(Path(ETCD_CERTS_DIR) / "client.pem").exists()
        or not Path(Path(ETCD_CERTS_DIR) / "client.key").exists()
    ):
        raise FileNotFoundError("Missing client certificate or key")
    Path(Path(ETCD_CERTS_DIR) / "ca.pem").write_text(server_ca_cert)

    try:
        output = subprocess.check_output(
            [
                "charmed-etcd.etcdctl",
                "--endpoints",
                uris,
                "--cert",
                f"{ETCD_CERTS_DIR}/client.pem",
                "--key",
                f"{ETCD_CERTS_DIR}/client.key",
                "--cacert",
                f"{ETCD_CERTS_DIR}/ca.pem",
                "get",
                f"{database_name}/foo",
            ],
        )
    except subprocess.CalledProcessError:
        return False
    return output.decode().strip().split("\n") == [f"{database_name}/foo", "bar"]


def create_table_cassandra(credentials: Dict[str, str], keyspace_name: str) -> bool:
    """Create a table in a Postgresql database."""
    cql = f"""
    CREATE TABLE IF NOT EXISTS {keyspace_name}.{TABLE_NAME} (
        id UUID PRIMARY KEY
    )
    """

    with _cqlsh_session(
        hosts=credentials["endpoints"].split(","),
        auth_provider=PlainTextAuthProvider(
            username=credentials["username"], password=credentials["password"]
        ),
        tls_ca=credentials["tls_ca"],
    ) as session:
        try:
            session.execute(cql)
        except Exception:
            return False
    return True


def insert_data_cassandra(credentials: Dict[str, str], keyspace_name: str) -> bool:
    """Insert specific testing data into a Cassandra table."""
    values = [("foo", 1), ("bar", 2)]

    try:
        with _cqlsh_session(
            hosts=credentials["endpoints"].split(","),
            auth_provider=PlainTextAuthProvider(
                username=credentials["username"],
                password=credentials["password"],
            ),
            tls_ca=credentials["tls_ca"],
        ) as session:
            for row in values:
                cql = f"""
                INSERT INTO {keyspace_name}.{TABLE_NAME} (name, value)
                VALUES ({row[0]!r}, {row[1]!r});
                """
                session.execute(cql)
        return True
    except Exception:
        return False


def check_inserted_data_cassandra(credentials: Dict[str, str], keyspace_name: str) -> bool:
    """Check that specific data are present in the Cassandra table."""
    expected_values = {("foo", 1), ("bar", 2)}

    try:
        with _cqlsh_session(
            hosts=credentials["endpoints"].split(","),
            auth_provider=PlainTextAuthProvider(
                username=credentials["username"],
                password=credentials["password"],
            ),
            tls_ca=credentials["tls_ca"],
        ) as session:
            rows = session.execute(f"SELECT name, value FROM {keyspace_name}.{TABLE_NAME};")
            rows_set = {(r.name, r.value) for r in rows}
            return expected_values.issubset(rows_set)
    except Exception:
        return False


@contextmanager
def _cqlsh_session(
    auth_provider: PlainTextAuthProvider,
    hosts: list[str],
    keyspace: str | None = None,
    tls_ca: str | None = None,
) -> Generator[Session, None, None]:
    ssl_context = SSLContext(PROTOCOL_TLS_CLIENT)

    if tls_ca:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = CERT_NONE
        ssl_context.load_verify_locations(cadata=tls_ca)
    else:
        ssl_context = None

    cluster = Cluster(
        auth_provider=auth_provider,
        contact_points=hosts,
        protocol_version=5,
        execution_profiles={
            EXEC_PROFILE_DEFAULT: ExecutionProfile(
                load_balancing_policy=TokenAwarePolicy(DCAwareRoundRobinPolicy())
            )
        },
        ssl_context=ssl_context,
    )
    session = cluster.connect()
    if keyspace:
        session.set_keyspace(keyspace)
    try:
        yield session
    finally:
        session.shutdown()
        cluster.shutdown()
