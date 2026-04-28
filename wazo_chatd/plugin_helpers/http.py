# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from werkzeug.wrappers import Request


def update_model_instance(model_instance, model_instance_data):
    for attribute_name, attribute_value in model_instance_data.items():
        if not hasattr(model_instance, attribute_name):
            raise TypeError(
                f'{model_instance.__class__.__name__} has no attribute {attribute_name}'
            )
        setattr(model_instance, attribute_name, attribute_value)


def build_public_url(request: Request) -> str:
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
    prefix = request.headers.get('X-Script-Name', '')
    path = request.path
    query = request.query_string.decode('ascii') if request.query_string else ''
    suffix = f'{path}?{query}' if query else path
    return f'{scheme}://{request.host}{prefix}{suffix}'
