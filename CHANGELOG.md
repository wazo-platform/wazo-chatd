# Changelog

## 26.06

* New endpoints:
  * `GET /connectors` — list registered connector backends and their tenant-configured state
  * `GET /connectors/{backend}/inventory` — list identities the provider reports this tenant owns
  * `GET /identities` — list all identities visible to the tenant, with pagination, search, sort, and filters
  * `POST /identities` — create an identity for a user
  * `GET /identities/{identity_uuid}` — get an identity by UUID
  * `PUT /identities/{identity_uuid}` — update an identity (partial; supports cross-user reassignment within the tenant)
  * `DELETE /identities/{identity_uuid}` — delete an identity

* Removed endpoints (superseded by the tenant-scoped `/identities` set above):
  * `GET /users/{user_uuid}/identities`
  * `POST /users/{user_uuid}/identities`
  * `GET /users/{user_uuid}/identities/{identity_uuid}`
  * `PUT /users/{user_uuid}/identities/{identity_uuid}`
  * `DELETE /users/{user_uuid}/identities/{identity_uuid}`

## 26.05

* New endpoints:
  * `GET /users/{user_uuid}/identities`
  * `POST /users/{user_uuid}/identities`
  * `GET /users/{user_uuid}/identities/{identity_uuid}`
  * `PUT /users/{user_uuid}/identities/{identity_uuid}`
  * `DELETE /users/{user_uuid}/identities/{identity_uuid}`
  * `GET /users/me/identities`
  * `POST /connectors/incoming`
  * `POST /connectors/incoming/{backend}`

* New read only parameters have been added to the room user resource:
  * `identity`

* New parameters have been added to the message creation endpoint:
  * `sender_identity_uuid`

* New read only parameter has been added to the message resource:
  * `delivery` (nested object with `type`, `backend`, and a `recipients` array
    containing per-recipient `identity`, `status`, and `updated_at`).
    Internal messages report `type=internal`, `backend=null`, and an empty
    `recipients` array.

* `POST /users/me/rooms` may now return `409` when a participant is unreachable
  via any registered connector or when no connector type is shared by all participants

* `POST /users/me/rooms/{room_uuid}/messages` may now return:
  * `202` when outbound delivery is accepted
  * `409` when `sender_identity_uuid` is required but missing, or when the resolved identity is not reachable

* New configuration: `connectors` to control which connector backends are loaded

## 26.02

* `POST`, `PATCH` and `PUT` request bodies to endpoints accepting JSON payload are systematically parsed as JSON, with or without a proper `Content-Type` header;
* `POST`, `PATCH` and `PUT` requests to endpoints accepting JSON payload and which are missing a body now return a `400` status response;
  previously those invalid requests could be treated as valid when Content-Type was missing and bodies were not parsed;

## 23.01

* Room can now have up to 100 users

* Changes to the following bus configuration keys:

  * key `exchange_name` now defaults to `wazo-headers`
  * key `exchange_type` was removed
  * key `subscribe` was removed

## 22.17

* New endpoint:
  * `POST /1.0/users/{user_uuid}/teams/presence`

## 22.16

* New query parameter `user_uuid` has been added to the `GET /1.0/users/me/rooms` endpoint.

## 22.07

* The following fields now include a timezone indication:

  * `created_at` for the following endpoints:
    * `GET /users/me/rooms/messages`
    * `GET /users/me/rooms/{room_uuid}/messages`
    * `POST /users/me/rooms/{room_uuid}/messages`
  * `last_activity` for the following endpoints:
    * `GET /users/presences`
    * `GET /users/{user_uuid}/presences`

## 21.12

* New read only parameters have been added to the `/status` API:

  * `master_tenant`

## 21.08

* The deprecated `sessions` parameter from user presence resource has been removed
* The `/user/<uuid>/presence` API and events now include the following values:

  * `line_state: progressing`

## 21.02

* New read only parameters have been added to the user presence resource:

  * `connected`

* The following presence parameter has been deprecated:

  * `sessions`

## 20.11

* New read only parameters have been added to the user presence resource:

  * `do_not_disturb`

## 20.09

* Deprecate SSL configuration

## 19.10

* New query parameter has been added to the `GET /1.0/users/me/rooms/messages` endpoint:

  * `distinct`

## 19.09

* New state has been added to the `PUT /1.0./users/{user_uuid}/presence` endpoint:

  * `away`

* New read only parameters have been added to the user presence resource:

  * `last_activity`

* New query parameters have been added to the `GET /1.0/users/me/rooms/{room_uuid}/messages`
  endpoint:

  * `from_date`

## 19.07

* New query parameter have been added to the `GET /1.0./users/me/rooms/{room_uuid}/messages`
  endpoint:

  * `offset`
  * `search`

* New endpoints:
  * `GET /1.0/users/me/rooms/messages`

* New read only parameters have been added to the message resource:

  * `room_uuid`

## 19.05

* New endpoints:
  * `GET /1.0/users/me/rooms`
  * `POST /1.0/users/me/rooms`
  * `GET /1.0/users/me/rooms/{room_uuid}/messages`
  * `POST /1.0/users/me/rooms/{room_uuid}/messages`

## 19.03

* New endpoints:
  * `GET /1.0/users/presences`
  * `GET /1.0/users/{user_uuid}/presences`
  * `PUT /1.0/users/{user_uuid}/presences`

## 19.02

* New endpoints:
  * `GET /1.0/api/api.yml`
  * `GET /1.0/config`
  * `GET /1.0/status`
