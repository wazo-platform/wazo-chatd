# Connectors API Changelog

Changes introduced by the `feat/connectors` branch.

## New Endpoints

### User Identity CRUD

- `GET /users/{user_uuid}/identities` — list identities for a user
- `POST /users/{user_uuid}/identities` — create an identity
- `GET /users/{user_uuid}/identities/{identity_uuid}` — get an identity
- `PUT /users/{user_uuid}/identities/{identity_uuid}` — update an identity
- `DELETE /users/{user_uuid}/identities/{identity_uuid}` — delete an identity

**ACL**: `chatd.users.{user_uuid}.identities.{read,create,update,delete}`

### Room Identities

- `GET /users/me/rooms/{room_uuid}/identities` — list usable identities for a room

**ACL**: `chatd.users.me.rooms.{room_uuid}.identities.read`

### Inbound Webhooks

- `POST /connectors/incoming` — generic inbound webhook dispatch
- `POST /connectors/incoming/{backend}` — inbound webhook with backend hint

No authentication (connector-level validation via signatures).
The `{backend}` path parameter is a hint for fast-path matching. If no
connector matches the hinted backend, the remaining connectors are tried
as fallback.

## Modified Endpoints

### Room User

New field added to the room user object:

| Field      | Type     | Description                                                              |
|------------|----------|--------------------------------------------------------------------------|
| `identity` | `string` | External identity of this participant. When set, the participant is reachable via the matching connector backend. |

### Room Creation (`POST /users/me/rooms`)

May now return `409` when a participant is unreachable via any registered connector.

### Message Creation (`POST /users/me/rooms/{room_uuid}/messages`)

New request field:

| Field                  | Type     | Description                                                    |
|------------------------|----------|----------------------------------------------------------------|
| `sender_identity_uuid` | `string` | UUID of the sender's identity to use for outbound delivery. Required when the room contains external participants. |

May now return:
- `202` when outbound delivery is accepted
- `409` when `sender_identity_uuid` is required but missing

### Message Responses

Applies to all endpoints returning messages.

New read-only fields:

| Field     | Type            | Description                                      |
|-----------|-----------------|--------------------------------------------------|
| `type`    | `string`        | Channel kind: `"internal"`, `"sms"`, etc. Defaults to `"internal"` when no connector metadata exists. |
| `backend` | `string \| null` | Provider name: `"twilio"`, `"vonage"`, etc. `null` for internal messages. |

## New Bus Events

### `chatd_message_delivery_status`

Published on delivery state changes (sending, sent, failed, retrying, dead_letter).

- **Type**: `MultiUserEvent` (delivered to all room participants)
- **Routing key**: `chatd.rooms.{room_uuid}.messages.{message_uuid}.delivery`
- **Payload**:
  ```json
  {
    "message_uuid": "message-uuid",
    "status": "sent",
    "timestamp": "2026-03-30T14:00:00+00:00",
    "backend": "twilio"
  }
  ```

## Extended Bus Events

### `chatd_user_room_message_created`

Now also emitted for **inbound connector messages** (previously only
internal messages). Same event structure, same routing key. The message
payload now includes `type` and `backend` fields.
