# Copyright 2022-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from flask import Response, request

from wazo_chatd.http import ErrorCatchingResource

from .log import make_logger
from .schemas import TeamsSubscriptionSchema
from .services import TeamsService

logger = make_logger(__name__)


class TeamsPresenceResource(ErrorCatchingResource):
    def __init__(self, teams_service: TeamsService):
        self.service = teams_service

    def post(self, user_uuid):
        validation_token = request.args.get('validationToken')

        if not self.service.is_connected(user_uuid):
            return '', 404

        if validation_token:
            # if validation_token, Microsoft is testing the endpoint and we must
            # respond with the token within 10 seconds
            return Response(validation_token, mimetype='text/plain')

        pushed_data = TeamsSubscriptionSchema().load(request.get_json())

        for subscription in pushed_data['value']:
            user_id = subscription['resource_data']['id']
            user_uuid = self.service.user_uuid_from_teams(user_id)
            if state := self.service.fetch_teams_presence(user_id):
                self.service.update_presence(state, user_uuid)

        return '', 200
