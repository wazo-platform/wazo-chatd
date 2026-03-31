# Connector Protocol - Developer Integration Guide

This guide explains how to build a connector backend for wazo-chatd. A connector is a bridge between wazo-chatd's room messaging system and an external messaging provider (Twilio, Vonage, WhatsApp Business API, email, etc.).

## Overview

Connectors are discovered at startup via [stevedore](https://docs.openstack.org/stevedore/) entry points. They are installed as separate Debian packages and have zero coupling to wazo-chatd internals. The connector only needs to implement a Python protocol - no HTTP, no Flask, no database access.

### How it works

```
  Outbound (user sends):
    Flask API → ConnectorRouter → DeliveryLoop → DeliveryExecutor → YourConnector.send()

  Inbound (external message arrives):
    Webhook/Poll → ConnectorRouter → YourConnector.can_handle() → YourConnector.on_event()
                                                                          ↓
                                                               DeliveryLoop → DeliveryExecutor
```

Your connector handles two things:
1. **Sending** messages to an external API
2. **Receiving** messages from an external API (webhooks, polling, or websockets)

Everything else (persistence, delivery tracking, retries, bus events) is handled by wazo-chatd.

## The Connector Protocol

Your connector class must implement the following interface. See `wazo_chatd.connectors.connector.Connector` for the full Protocol definition.

### Class attributes

```python
from typing import ClassVar

class MyConnector:
    backend: ClassVar[str] = 'my-provider'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')
```

| Attribute | Description |
|-----------|-------------|
| `backend` | Unique identifier for your provider (e.g. `"twilio"`, `"vonage"`, `"mailgun"`) |
| `supported_types` | Tuple of messaging types this backend supports (e.g. `("sms", "mms", "whatsapp")`) |

### `configure(type_, provider_config, connector_config)`

Called once after instantiation. Receives two configuration sources:

```python
def configure(
    self,
    type_: str,
    provider_config: Mapping[str, Any],
    connector_config: Mapping[str, Any],
) -> None:
    self._type = type_
    self._api_key = provider_config['api_key']
    self._mode = str(connector_config.get('mode', 'webhook'))
```

| Parameter | Source | Example |
|-----------|--------|---------|
| `type_` | `ChatProvider.type_` | `"sms"`, `"whatsapp"` |
| `provider_config` | `ChatProvider.configuration` JSONB (per-tenant, managed by confd) | `{"api_key": "...", "sender_id": "+15551234"}` |
| `connector_config` | `/etc/wazo-chatd/conf.d/` (system-level) | `{"mode": "webhook", "polling_interval": 30}` |

### `send(message) -> str`

Send a message through your external API. Returns the provider's message ID.

```python
from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.types import OutboundMessage

def send(self, message: OutboundMessage) -> str:
    try:
        result = self._client.messages.create(
            to=message.recipient_alias,
            body=message.body,
            from_=message.sender_alias,
        )
        return result.id
    except ProviderError as exc:
        raise ConnectorSendError(str(exc)) from exc
```

**Key points:**
- Raise `ConnectorSendError` on failure - wazo-chatd handles retries
- Return the external message ID as a string
- Can be sync or async. Sync implementations are automatically wrapped with `asyncio.to_thread()`
- `message.metadata` may contain `idempotency_key` - pass it to the provider if supported

**OutboundMessage fields:**

| Field | Type | Description |
|-------|------|-------------|
| `room_uuid` | `str` | Room this message belongs to |
| `message_uuid` | `str` | Unique message identifier |
| `sender_uuid` | `str` | Wazo user UUID of the sender |
| `body` | `str` | Message content |
| `sender_alias` | `str` | Sender's external identity (e.g. `"+15551234"`) |
| `recipient_alias` | `str` | Recipient's external identity |
| `metadata` | `Mapping` | Extra data including optional `idempotency_key` |

### `can_handle(transport, raw_data) -> bool`

Cheap pre-filter called before `on_event()`. Inspect headers or content-type to quickly determine if this webhook is for your connector.

```python
def can_handle(self, transport: str, raw_data: Mapping[str, Any]) -> bool:
    if transport != 'webhook':
        return True

    headers = raw_data.get('_headers', {})
    return 'X-My-Provider-Signature' in headers
```

**When called:** Before `on_event()`, during webhook dispatch. Multiple connectors may be registered; `can_handle` avoids calling `on_event()` on connectors that clearly don't match.

**What to check:** Headers, user-agent, content-type, or any cheap signal. Do NOT do full parsing or signature validation here.

**The `raw_data` dict includes:**

| Key | Description |
|-----|-------------|
| `_headers` | Dict of HTTP headers from the webhook request |
| `_content_type` | Content-Type header value |
| *(other keys)* | The actual request body (JSON or form-encoded) |

### `on_event(transport, raw_data) -> InboundMessage | None`

Parse an incoming event into an `InboundMessage`. Return `None` to skip (e.g. status callbacks, delivery receipts).

```python
from wazo_chatd.connectors.types import InboundMessage

def on_event(
    self,
    transport: str,
    raw_data: Mapping[str, Any],
) -> InboundMessage | None:
    if transport == 'webhook':
        body = raw_data.get('body')
        if not body:
            return None

        return InboundMessage(
            sender=raw_data['from'],
            recipient=raw_data['to'],
            body=body,
            backend=self.backend,
            external_id=raw_data['message_id'],
            metadata={
                'idempotency_key': raw_data.get('idempotency_token', ''),
            },
        )
    return None
```

**Signature validation** is your responsibility. Verify the webhook signature inside `on_event()` and return `None` if invalid.

**Idempotency:** If the provider supplies a deduplication key, include it as `idempotency_key` in `InboundMessage.metadata`. wazo-chatd uses this to prevent duplicate message ingestion via a GIN-indexed JSONB lookup.

**InboundMessage fields:**

| Field | Type | Description |
|-------|------|-------------|
| `sender` | `str` | External identity of the sender |
| `recipient` | `str` | External identity of the recipient |
| `body` | `str` | Message content |
| `backend` | `str` | Your backend name (must match `cls.backend`) |
| `external_id` | `str` | Provider's message ID |
| `metadata` | `Mapping` | Extra data, including optional `idempotency_key` |

### `normalize_identity(raw_identity) -> str`

Normalize an external identity to its canonical form. Used for capability resolution: if this method succeeds for a given identity, your connector type can reach that participant.

```python
import re

_E164 = re.compile(r'^\+[1-9]\d{6,14}$')

def normalize_identity(self, raw_identity: str) -> str:
    if _E164.match(raw_identity):
        return raw_identity
    raise ValueError(f'Not a valid phone number: {raw_identity}')
```

Raise `ValueError` if the identity doesn't match your connector's expected format. This is how wazo-chatd determines which connectors can reach which participants.

### `listen(on_message)` and `stop()`

For connectors that use polling or websockets instead of webhooks.

```python
def listen(self, on_message: Callable[[InboundMessage], None]) -> None:
    # For webhook-only connectors: no-op
    pass

    # For polling connectors:
    while not self._stopped:
        messages = self._client.poll_new_messages()
        for msg in messages:
            inbound = self.on_event('poll', msg)
            if inbound:
                on_message(inbound)
        time.sleep(self._polling_interval)

def stop(self) -> None:
    self._stopped = True
```

For webhook-only connectors, both methods are no-ops.

## Packaging and Discovery

### Entry point registration

Register your connector via setuptools entry points in `setup.cfg` or `pyproject.toml`:

```ini
# setup.cfg
[options.entry_points]
wazo_chatd.connectors =
    my-provider = wazo_chatd_connector_myprovider.connector:MyConnector
```

```toml
# pyproject.toml
[project.entry-points."wazo_chatd.connectors"]
my-provider = "wazo_chatd_connector_myprovider.connector:MyConnector"
```

The entry point name should match your `backend` class attribute.

### Package structure

```
wazo-chatd-connector-myprovider/
    setup.cfg (or pyproject.toml)
    wazo_chatd_connector_myprovider/
        __init__.py
        connector.py      # MyConnector class
```

### Installation

```bash
apt install wazo-chatd-connector-myprovider
# or during development:
pip install -e ./wazo-chatd-connector-myprovider
```

wazo-chatd discovers installed connectors at startup via stevedore. No configuration changes needed in wazo-chatd itself.

### Enabling/disabling

Backends are controlled via wazo-chatd configuration:

```yaml
# /etc/wazo-chatd/conf.d/connectors.yml
enabled_connectors:
  my-provider: true
  twilio: true
  internal: true  # always enabled by default
```

## Webhook Configuration

wazo-chatd exposes two webhook endpoints for inbound messages:

- `POST /connectors/incoming` - generic, tries all connectors
- `POST /connectors/incoming/<backend>` - backend hint for faster matching

Configure your external provider to send webhooks to either URL. The `<backend>` path is a convenience hint that prioritizes matching connectors but falls back to trying all registered connectors if no match is found.

The dispatch flow:
1. `can_handle('webhook', raw_data)` is called on each connector (hint-matched first)
2. First connector returning `True` gets `on_event('webhook', raw_data)` called
3. If `on_event` returns an `InboundMessage`, it's enqueued for processing
4. If it returns `None`, the next matching connector is tried

## Delivery Lifecycle

Understanding the delivery lifecycle helps when implementing error handling in `send()`:

```
PENDING → SENDING → SENT → DELIVERED
              │
              ▼
           FAILED → RETRYING → SENDING (retry loop, max 3 attempts)
              │
              ▼
         DEAD_LETTER (terminal, requires manual intervention)
```

- Raise `ConnectorSendError` on transient failures - wazo-chatd retries automatically
- Return the external message ID on success
- wazo-chatd publishes `chatd_message_delivery_status` bus events on each state transition

## Complete Example

```python
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.types import InboundMessage, OutboundMessage

_E164 = re.compile(r'^\+[1-9]\d{6,14}$')


class VonageConnector:
    backend: ClassVar[str] = 'vonage'
    supported_types: ClassVar[tuple[str, ...]] = ('sms',)

    def __init__(self) -> None:
        self._api_key: str = ''
        self._api_secret: str = ''
        self._client = None

    def configure(
        self,
        type_: str,
        provider_config: Mapping[str, Any],
        connector_config: Mapping[str, Any],
    ) -> None:
        self._api_key = provider_config.get('api_key', '')
        self._api_secret = provider_config.get('api_secret', '')
        # Initialize your SDK client here

    def send(self, message: OutboundMessage) -> str:
        try:
            response = self._client.sms.send_message({
                'from': message.sender_alias,
                'to': message.recipient_alias,
                'text': message.body,
            })
            return response['messages'][0]['message-id']
        except Exception as exc:
            raise ConnectorSendError(str(exc)) from exc

    def can_handle(
        self,
        transport: str,
        raw_data: Mapping[str, Any],
    ) -> bool:
        if transport != 'webhook':
            return True
        headers = raw_data.get('_headers', {})
        return 'X-Vonage-Signature' in headers

    def on_event(
        self,
        transport: str,
        raw_data: Mapping[str, Any],
    ) -> InboundMessage | None:
        if transport != 'webhook':
            return None

        body = raw_data.get('text')
        if not body:
            return None

        return InboundMessage(
            sender=raw_data.get('msisdn', ''),
            recipient=raw_data.get('to', ''),
            body=body,
            backend=self.backend,
            external_id=raw_data.get('messageId', ''),
        )

    def listen(self, on_message: Callable[[InboundMessage], None]) -> None:
        pass

    def stop(self) -> None:
        pass

    def normalize_identity(self, raw_identity: str) -> str:
        if _E164.match(raw_identity):
            return raw_identity
        raise ValueError(f'Not a valid phone number: {raw_identity}')
```
