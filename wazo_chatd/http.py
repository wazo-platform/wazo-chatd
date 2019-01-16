# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from flask_restful import Resource
from xivo import mallow_helpers
from xivo import rest_api_helpers
from xivo.auth_verifier import AuthVerifier

auth_verifier = AuthVerifier()


class ErrorCatchingResource(Resource):
    method_decorators = (
        [mallow_helpers.handle_validation_exception, rest_api_helpers.handle_api_exception]
        + Resource.method_decorators
    )


class AuthResource(ErrorCatchingResource):
    method_decorators = [auth_verifier.verify_token] + ErrorCatchingResource.method_decorators
