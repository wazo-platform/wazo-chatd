# Copyright 2022-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from flask import request, Response
from flask_restful import Resource


logger = logging.getLogger(__name__)


class TeamsResource(Resource):
    def __init__(self, teams_service):
        self.service = teams_service

    def post(self, user_uuid):
        validation_token = request.args.get('validationToken')

        if validation_token:
            # if validation_token, Microsoft is testing the endpoint and we must
            # respond with the token within 10 seconds
            return Response(validation_token, mimetype='text/plain')

        payload = request.get_json()
        self.service.update_presence(payload, user_uuid)
        return '', 200
