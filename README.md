# Charmed Data Integrator Operator

## Overview

This charm allows a user to automatically create and manage product credentials needed to authenticate with different kinds of data platform charmed products:
* [MongoDB](https://github.com/canonical/mongodb-operator)
* [MySQL](https://github.com/canonical/mysql-operator)
* [PostgreSQL](https://github.com/canonical/postgresql-operator)
* [Kafka](https://github.com/canonical/kafka-operator)
* [OpenSearch](https://github.com/canonical/opensearch-operator)

It grants access to several charmed applications developed by the data-platform by handling the management of their credentials. In particular, a user can request access to a database (MySQL, PostgreSQL and MongoDB), a topic (Kafka), or an index (OpenSearch). Moreover, a user can require additional privileges by specifying extra-user-roles.

This charm enables applications or users outside Juju to connect with the desired charmed application by providing credentials and endpoints that are needed to use the desired product.


## Config options

The supported configuration options are the following:

database-name - `string`; The desired database name for which the access will be granted.

topic-name - `string`; The topic name for which the access is granted.

index-name - `string`; The index name for which the access is granted. [OPENSEARCH ONLY]

extra-user-roles - `string`; a comma-separated list of values that contains the required extra roles `admin` in case of a database or opensearch, or `producer`, `consumer` in case of Kafka.

| Product    | database-name      | topic-name         | index-name         | extra-user-roles   |
|------------|--------------------|--------------------|--------------------|--------------------|
| MySQL      | :heavy_check_mark: |                    |                    | :white_check_mark: |
| PostgreSQL | :heavy_check_mark: |                    |                    | :white_check_mark: |
| MongoDB    | :heavy_check_mark: |                    |                    | :white_check_mark: |
| Kafka      |                    | :heavy_check_mark: |                    | :heavy_check_mark: |
| OpenSearch |                    |                    | :heavy_check_mark: | :white_check_mark: |

:heavy_check_mark: -> mandatory field
:white_check_mark: -> optional field

## Usage

### Basic Usage
To deploy a unit of the Data Integrator Charm.

#### Charmhub
```shell
juju deploy data-integrator --channel edge
```
#### From source
```shell
git clone https://github.com/canonical/data-integrator.git
cd data-integrator/
sudo snap install charmcraft --classic
charmcraft pack
```
Then,
```shell
juju deploy ./data-integrator_ubuntu-22.04-amd64.charm
```

#### Configuration

If you want to require access to a database, specify the `database-name` parameter:

```shell
juju config data-integrator database-name=test-database
```
In addition, required `extra-user-roles` can be specified.

```shell
juju config data-integrator database-name=test-database extra-user-roles=admin
```

Instead, for Kafka please configure the desired `topic-name`:

```shell
juju config data-integrator topic-name=test-topic extra-user-roles=producer,consumer
```

#### Relation with desired application

In order to related to the desired data-platform application use the following command:

```shell
juju relate data-integrator <application>
```

After the relation has been created, the credentials and connection information can be retrieved with an action.

> **IMPORTANT** In order to change the current credentials (username and password), remove the relation with the application and establish a new one.

When the relation is removed, the access with the previous credentials will be removed.

```shell
juju remove-relation data-integrator <application>
```

> If you need to modify `database-name`, `topic-name`, `index-name`, or `extra-user-roles` and the relation has been already established, you need to remove the relation and then change the `database-name`, `topic-name`, `index-name`, or `extra-user-roles`, and finally relate the data-integrator with the desidered application.

#### Retrieve credentials

In order to retrieve the credentials use the following action:

```shell
juju run-action data-integrator/leader get-credentials --wait
```

## Tutorial

#### Relate Data Integrator with MongoDB

As first step, deploy the data-integrator charm with the :
```shell
juju deploy data-integrator --channel edge --config database-name=test-database
juju deploy mongodb --channel dpe/edge
```
Wait for `watch -c juju status --relations --color` to show:

```
Model            Controller        Cloud/Region         Version  SLA          Timestamp
test-integrator  lxd-controller-1  localhost/localhost  2.9.34   unsupported  13:05:56Z

App              Version  Status   Scale  Charm            Channel   Rev  Exposed  Message
data-integrator           blocked      1  data-integrator             79  no       Please relate the data-integrator with the desired product
mongodb                   active       1  mongodb          dpe/edge   99  no

Unit                 Workload  Agent  Machine  Public address  Ports      Message
data-integrator/79*  blocked   idle   99       10.91.92.137               Please relate the data-integrator with the desired product
mongodb/3*           active    idle   100      10.91.92.227    27017/tcp

Machine  State    Address       Inst id          Series  AZ  Message
99       started  10.91.92.137  juju-554175-99   jammy       Running
100      started  10.91.92.227  juju-554175-100  focal       Running

Relation provider                      Requirer                               Interface              Type  Message
data-integrator:data-integrator-peers  data-integrator:data-integrator-peers  data-integrator-peers  peer
mongodb:database-peers                 mongodb:database-peers                 mongodb-peers          peer

```


Relate the two applications with:
```shell
juju relate data-integrator mongodb
```
Wait for `watch -c juju status --relations --color` to show:
```
Model            Controller        Cloud/Region         Version  SLA          Timestamp
test-integrator  lxd-controller-1  localhost/localhost  2.9.34   unsupported  13:06:58Z

App              Version  Status  Scale  Charm            Channel   Rev  Exposed  Message
data-integrator           active      1  data-integrator             79  no
mongodb                   active      1  mongodb          dpe/edge   99  no

Unit                 Workload  Agent  Machine  Public address  Ports      Message
data-integrator/79*  active    idle   99       10.91.92.137
mongodb/3*           active    idle   100      10.91.92.227    27017/tcp

Machine  State    Address       Inst id          Series  AZ  Message
99       started  10.91.92.137  juju-554175-99   jammy       Running
100      started  10.91.92.227  juju-554175-100  focal       Running

Relation provider                      Requirer                               Interface              Type     Message
data-integrator:data-integrator-peers  data-integrator:data-integrator-peers  data-integrator-peers  peer
mongodb:database                       data-integrator:mongodb                mongodb_client         regular
mongodb:database-peers                 mongodb:database-peers                 mongodb-peers          peer
```
To retrieve information such as the username, password, and database. Enter:
```shell
juju run-action data-integrator/leader get-credentials --wait
```
This should output something like:
```yaml
unit-data-integrator-79:
  UnitId: data-integrator/79
  id: "30"
  results:
    mongodb:
      database: test-database
      endpoints: 10.91.92.227
      password: D25MgMVQ3wGUxNsFR35V42KlUoNSWZd6
      replset: mongodb
      uris: mongodb://relation-141:D25MgMVQ3wGUxNsFR35V42KlUoNSWZd6@10.91.92.227/test-database?replicaSet=mongodb&authSource=admin
      username: relation-141
    ok: "True"
  status: completed
  timing:
    completed: 2023-01-20 13:08:22 +0000 UTC
    enqueued: 2023-01-20 13:08:18 +0000 UTC
    started: 2023-01-20 13:08:21 +0000 UTC
```
Connect to MongoDB with  the value listed under `uris:` *(Note: your hostnames, usernames, and passwords will likely be different.)*

The same process can be done with all other products supported by the Data Platform Team.

## Relations

Supported [relations](https://juju.is/docs/olm/relations):

- `mongodb_client`
- `mysql_client`
- `postgresql_client`
- `kafka_client`
- `opensearch_client`

All applications that use the (`data_interfaces`)[https://github.com/canonical/data-platform-libs] library are supported by the Data Integrator Charm.

## Security
Security issues in the Charmed Data Integrator Operator can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.


## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/data-integrator/CONTRIBUTING.md) for developer guidance.
