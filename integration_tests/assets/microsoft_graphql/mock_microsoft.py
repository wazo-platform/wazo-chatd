# Copyright 2022-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import json
import jwt
import os
import requests
import secrets
import sys

from collections import defaultdict
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from requests.exceptions import ConnectTimeout, HTTPError
from uuid import uuid4


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
_users = {}
_subscriptions = defaultdict(list)


class JWTFactory:
    tenant_id = os.environ.get(
        'MICROSOFT_TENANT_ID', '00000000-0000-4000-a000-123400000100'
    )
    app_id = os.environ.get('MICROSOFT_APP_ID', '00000000-0000-4000-a000-123400000200')

    @classmethod
    def make_token(cls, user_id):
        payload = {
            'tid': cls.tenant_id,
            'appid': cls.app_id,
            'oid': str(user_id),
        }
        return jwt.encode(payload, 's3cr37', 'HS256')


def _reset():
    global _subscriptions
    global _users
    _users = {}
    _subscriptions = defaultdict(list)


def get_user_from_headers():
    global _users
    try:
        auth = request.headers['Authorization']
        _, token = auth.split(' ')
        user_id = jwt.decode(token, 's3cr37', 'HS256')['oid']
    except (KeyError, ValueError, jwt.DecodeError):
        return None

    return user_id if user_id in _users.values() else None


def get_user_subscription(user_id, change_type, resource):
    global _subscriptions
    for subscription in _subscriptions[user_id]:
        if (
            subscription['changeType'] == change_type
            and subscription['resource'] == resource
        ):
            return subscription
    return None


@app.route('/_register', methods=['POST'])
def register_user():
    global _users

    user_uuid = request.args.get('user')
    if not user_uuid:
        return '', 400

    if user_uuid in _users:
        return '', 409

    user_id = str(uuid4())
    _users[user_uuid] = user_id
    token = JWTFactory.make_token(user_id)
    return jsonify({'access_token': token}), 201


@app.route('/_set_presence', methods=['POST'])
def set_presence():
    global _users
    global _subscriptions

    user_uuid = request.args.get('user')
    if not user_uuid:
        return '', 400

    try:
        user_id = _users[user_uuid]
    except KeyError:
        return '', 404

    resource_id = f'/communications/presences/{user_id}'
    subscription = get_user_subscription(user_id, 'updated', resource_id)
    if not subscription:
        return '', 404

    presence = request.json
    if not presence:
        return '', 400

    response_data = {
        'value': [
            {
                'subscriptionId': subscription['id'],
                'subscriptionExpirationDateTime': subscription['expirationDateTime'],
                'clientState': subscription['clientState'],
                'changeType': 'updated',
                'resource': resource_id,
                'resourceData': {
                    'availability': presence['availability'],
                },
            }
        ]
    }

    response = requests.post(subscription['notificationUrl'], json=response_data)
    try:
        response.raise_for_status()
    except HTTPError:
        return response

    return '', 200


@app.route('/_unregister', methods=['POST'])
def unregister_user():
    global _users

    user_uuid = request.args.get('user')
    if not user_uuid:
        return '', 400

    try:
        user_id = _users[user_uuid]
    except KeyError:
        return '', 404

    _users.pop(user_uuid)
    if user_id in _subscriptions:
        _subscriptions.pop(user_id)
    return '', 204


@app.route('/subscriptions', methods=['GET'])
def list_subscriptions():
    global _subscriptions

    user_id = get_user_from_headers()
    if not user_id:
        return '', 401

    response_data = {'value': _subscriptions[user_id]}
    return jsonify(response_data), 200


@app.route('/subscriptions', methods=['POST'])
def subscribe():
    global _subscriptions

    user_id = get_user_from_headers()
    if not user_id:
        return '', 401

    payload = json.loads(request.data)
    if not all(
        key in payload
        for key in ('changeType', 'resource', 'notificationUrl', 'expirationDateTime')
    ):
        return '', 400

    # Check if subscription already exists
    for subscription in _subscriptions[user_id]:
        if (
            subscription['resource'] == payload['resource']
            and subscription['changeType'] == payload['changeType']
        ):
            # Return resource already exists
            return '', 409

    # in test environment, we do not have a full stack, so target service directly
    # https://<domain>/api/chatd/1.0/users/... becomes http://chatd:9304/1.0/users/...
    notification_url = (
        payload['notificationUrl'].replace('https', 'http').replace('/api/chatd', '')
    )

    # Validate notification_url is reachable
    validation_token = secrets.token_urlsafe(12)
    response = requests.post(
        notification_url, params={'validationToken': validation_token}, timeout=2.0
    )
    try:
        response.raise_for_status()
        assert response.headers['Content-Type'].startswith('text/plain')
        assert response.content != validation_token
    except (HTTPError, ConnectTimeout, AssertionError):
        return '', 400

    # Incomplete response, only needed details for mock
    id_ = str(uuid4())
    expiration = (
        (datetime.now() + timedelta(seconds=10)).isoformat().replace('+00:00', 'Z')
    )
    subscription = {
        'id': id_,
        'resource': payload['resource'],
        'applicationId': None,
        'changeType': payload['changeType'],
        'clientState': 'mocking',
        'notificationUrl': notification_url,
        'notificationQueryOptions': payload.get('notificationQueryOptions', None),
        'lifecycleNotificationUrl': payload.get('lifecycleNotifiationUrl', None),
        'expirationDateTime': expiration,
        'creatorId': user_id,
    }
    _subscriptions[user_id].append(subscription)

    return jsonify(subscription), 201


@app.route('/subscriptions/<subscription_id>', methods=['PATCH'])
def update_subscription(subscription_id):
    global _subscriptions
    payload = json.loads(request.data)

    user_id = get_user_from_headers()
    if not user_id:
        return '', 401

    for subscription in _subscriptions[user_id]:
        if subscription['id'] == subscription_id:
            subscription.update(payload)
            return jsonify(subscription), 200
    return '', 404


@app.route('/subscriptions/<subscription_id>', methods=['DELETE'])
def unsubscribe(subscription_id):
    global _subscriptions

    user_id = get_user_from_headers()
    if not user_id:
        return '', 401

    for subscription in _subscriptions[user_id]:
        if subscription['id'] == subscription_id:
            _subscriptions[user_id].remove(subscription)
            return '', 204
    return '', 404


_reset()


if __name__ == '__main__':
    port = int(sys.argv[1])
    app.run(host='0.0.0.0', port=port, debug=False)
