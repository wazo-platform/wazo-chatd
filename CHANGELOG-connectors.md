# Connectors API Changelog

Changes introduced by the `feat/connectors` branch.

## New Endpoints

### `GET /users/me/aliases`

List messaging aliases (external identities) for the authenticated user.

- **ACL**: `chatd.users.me.aliases.read`
- **Query parameters**:
  - `type` (optional): comma-separated filter, e.g. `?type=sms,whatsapp`
- **Response**:
  ```json
  {
    "items": [
      {
        "uuid": "alias-uuid",
        "type": "sms",
        "backend": "twilio",
        "identity": "+15551234567"
      }
    ],
    "total": 1
  }
  ```

### `POST /connectors/incoming`

Generic inbound webhook endpoint. Tries all registered connectors using
two-phase dispatch (`can_handle` pre-filter, then `on_event` parsing).

- **No authentication** (connector-level validation via signatures)
- **Accepts**: `application/json` or `application/x-www-form-urlencoded`
- **Response**: `204 No Content` on success, `404` if no connector matched

## Modified Endpoints

### Room Responses

Applies to all endpoints returning rooms:
- `POST /users/me/rooms`
- `GET /users/me/rooms`

New computed field added to the room object:

| Field          | Type       | Description                                                        |
|----------------|------------|--------------------------------------------------------------------|
| `capabilities` | `string[]` | Connector types available to all participants in the room. Computed from installed connectors and participant identities. `["internal"]` for internal-only rooms. |

Example response:
```json
{
  "uuid": "room-uuid",
  "tenant_uuid": "tenant-uuid",
  "users": [
    { "uuid": "user-a", "tenant_uuid": "tenant-uuid", "wazo_uuid": "wazo-uuid", "identity": null },
    { "uuid": "ext-uuid", "tenant_uuid": "tenant-uuid", "wazo_uuid": "wazo-uuid", "identity": "+15559876" }
  ],
  "capabilities": ["sms", "whatsapp"]
}
```

### `POST /connectors/incoming/<backend>`

The `<backend>` path parameter is now a **hint** for fast-path matching, not
a definitive filter. If no connector matches the hinted backend, the
remaining connectors are tried as fallback.

### Message Responses

Applies to all endpoints returning messages:
- `POST /rooms/{room_uuid}/messages`
- `GET /rooms/{room_uuid}/messages`

New fields added to the message object:

| Field     | Type            | Direction | Description                                      |
|-----------|-----------------|-----------|--------------------------------------------------|
| `type`    | `string`        | response  | Channel kind: `"internal"`, `"sms"`, `"whatsapp"`, etc. Defaults to `"internal"` when no connector metadata exists. |
| `backend` | `string \| null` | response  | Provider name: `"twilio"`, `"vonage"`, etc. `null` for internal messages. |
| `sender_alias_uuid` | `string \| null` | request | UUID of the sender's alias to use for delivery. Determines which connector and identity to send from. Omit for internal messages. |

Example request:
```json
{
  "content": "Hello via SMS",
  "sender_alias_uuid": "alias-uuid"
}
```

Example response:
```json
{
  "uuid": "message-uuid",
  "content": "Hello",
  "type": "sms",
  "backend": "twilio",
  "user_uuid": "user-uuid",
  "tenant_uuid": "tenant-uuid",
  "wazo_uuid": "wazo-uuid",
  "created_at": "2026-03-30T14:00:00+00:00",
  "room": { "uuid": "room-uuid" }
}
```

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
