# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from marshmallow import ValidationError
from flask import request

from xivo.auth_verifier import required_acl
from xivo.mallow.validate import Length
from xivo.tenant_flask_helpers import token

from wazo_chatd.http import AuthResource
from wazo_chatd.database.models import Room, RoomUser, RoomMessage

from .exceptions import DuplicateUserException
from .schemas import (
    ListRequestSchema,
    MessageListRequestSchema,
    MessageSchema,
    RoomSchema,
)


class UserRoomListResource(AuthResource):
    def __init__(self, service):
        self._service = service

    @required_acl('chatd.users.me.rooms.create')
    def post(self):
        room_args = RoomSchema().load(request.get_json())

        if self._is_duplicate_user(room_args['users']):
            raise DuplicateUserException()

        if not self._current_user_is_in_room(token.user_uuid, room_args):
            self._add_current_user(room_args, token.user_uuid)

        try:
            Length(min=2,max=100)(room_args['users'])
        except ValidationError as error:
            raise ValidationError({'users': error.messages})

        room_args['tenant_uuid'] = token.tenant_uuid
        room_args['users'] = [RoomUser(**user) for user in room_args['users']]
        room = Room(**room_args)

        room = self._service.create(room)
        return RoomSchema().dump(room), 201

    def _current_user_is_in_room(self, current_user_uuid, room_args):
        return any(
            current_user_uuid == str(user['uuid']) for user in room_args['users']
        )

    def _add_current_user(self, room_args, user_uuid):
        room_args['users'].append({'uuid': user_uuid})

    def _is_duplicate_user(self, users):
        unique = set(user['uuid'] for user in users)
        if len(unique) != len(users):
            return True
        return False

    @required_acl('chatd.users.me.rooms.read')
    def get(self):
        filter_parameters = {'user_uuid': token.user_uuid}
        rooms = self._service.list_([token.tenant_uuid], **filter_parameters)
        filtered = total = self._service.count([token.tenant_uuid], **filter_parameters)
        return {
            'items': RoomSchema().dump(rooms, many=True),
            'filtered': filtered,
            'total': total,
        }


class UserMessageListResource(AuthResource):
    def __init__(self, service):
        self._service = service

    @required_acl('chatd.users.me.rooms.messages.read')
    def get(self):
        filter_parameters = MessageListRequestSchema().load(request.args)
        messages = self._service.list_user_messages(
            token.tenant_uuid, token.user_uuid, **filter_parameters
        )
        filtered = self._service.count_user_messages(
            token.tenant_uuid, token.user_uuid, **filter_parameters
        )
        total = self._service.count_user_messages(token.tenant_uuid, token.user_uuid)
        return {
            'items': MessageSchema().dump(messages, many=True),
            'filtered': filtered,
            'total': total,
        }


class UserRoomMessageListResource(AuthResource):
    def __init__(self, service):
        self._service = service

    @required_acl('chatd.users.me.rooms.{room_uuid}.messages.create')
    def post(self, room_uuid):
        room = self._service.get([token.tenant_uuid], room_uuid)
        message_args = MessageSchema().load(request.get_json())
        message_args['user_uuid'] = token.user_uuid
        message_args['tenant_uuid'] = token.tenant_uuid
        message = RoomMessage(**message_args)

        message = self._service.create_message(room, message)
        return MessageSchema().dump(message), 201

    @required_acl('chatd.users.me.rooms.{room_uuid}.messages.read')
    def get(self, room_uuid):
        filter_parameters = ListRequestSchema().load(request.args)
        room = self._service.get([token.tenant_uuid], room_uuid)
        messages = self._service.list_messages(room, **filter_parameters)
        filtered = self._service.count_messages(room, **filter_parameters)
        total = self._service.count_messages(room)
        return {
            'items': MessageSchema().dump(messages, many=True),
            'filtered': filtered,
            'total': total,
        }
