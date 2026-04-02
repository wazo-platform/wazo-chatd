# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import sys

from flask import Flask, jsonify, request

app = Flask(__name__)

_config: dict[str, str] = {
    'send_behavior': 'succeed',
    'external_id': '',
    'error_message': 'Test connector failure',
}

_sent_messages: list[dict[str, str]] = []


@app.route('/config', methods=['GET'])
def get_config():
    return jsonify(_config)


@app.route('/config', methods=['PUT'])
def set_config():
    _config.update(request.get_json(force=True))
    return jsonify(_config)


@app.route('/sent', methods=['GET'])
def list_sent():
    return jsonify(_sent_messages)


@app.route('/sent', methods=['POST'])
def report_sent():
    _sent_messages.append(request.get_json(force=True))
    return '', 204


@app.route('/reset', methods=['POST'])
def reset():
    _config.clear()
    _config.update(
        {
            'send_behavior': 'succeed',
            'external_id': '',
            'error_message': 'Test connector failure',
        }
    )
    _sent_messages.clear()
    return '', 204


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    app.run(host='0.0.0.0', port=port)
