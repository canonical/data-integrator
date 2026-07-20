# Terraform module for data-integrator

This is a Terraform module facilitating the deployment of the Data Integrator charm with the [Terraform Juju provider](https://github.com/juju/terraform-provider-juju/). For more information, refer to the provider [documentation](https://registry.terraform.io/providers/juju/juju/latest/docs).

## Requirements

| Name | Version |
|------|---------|
| `Terraform` | >= 1.6 |
| `Juju provider` | ~> 2.0  |

## Providers

| Name | Version |
| ---- | ------- |
| `juju` | ~> 2.0 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| `juju_application.data_integrator` | [Juju application](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| `app_name` | Application name | `string` | `"data-integrator"` | no |
| `base` | Charm base (old name: series) | `string` | `null` | no |
| `channel` | Charm channel | `string` | `"latest/edge"` | no |
| `config` | Data Integrator charm configuration options | <pre>object({<br/>  consumer-group-prefix     = optional(string)<br/>  database-name             = optional(string)<br/>  entity-permissions        = optional(string)<br/>  entity-type               = optional(string)<br/>  extra-group-roles         = optional(string)<br/>  extra-user-roles          = optional(string)<br/>  index-name                = optional(string)<br/>  keyspace-name             = optional(string)<br/>  mtls-cert                 = optional(string)<br/>  prefix-name               = optional(string)<br/>  requested-entities-secret = optional(string)<br/>  topic-name                = optional(string)<br/>})</pre> | `{}` | no |
| `constraints`       | String listing constraints for this application | `string` | `null` | no |
| `endpoint_bindings` | Set of endpoint bindings | <pre>set(object({<br/>    space    = string<br/>    endpoint = optional(string)<br/>  }))</pre> | `[]` | no |
| `machines` | List of machines for placement | `set(string)` | `[]` | no |
| `model_uuid` | Model UUID | `string` | n/a | yes |
| `revision` | Charm revision | `number` | `null` | no |
| `storage_directives` | Map of storage used by the application | `map(string)` | `{}` | no |
| `units` | Charm units | `number` | `1` | no |

## Outputs

| Name | Description |
|------|-------------|
| `application` | Object representing the deployed Data Integrator application |
| `offers` | Map of all offers exposed by the single charm. |
| `provides` | Map of all "provides" endpoints |
| `requires` | Map of all "requires" endpoints |
