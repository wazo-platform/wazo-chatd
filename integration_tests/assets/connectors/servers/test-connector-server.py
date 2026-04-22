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
_scan_queue: list[dict[str, str]] = []
_tracked_statuses: dict[str, dict[str, str]] = {}


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


@app.route('/scan', methods=['GET'])
def scan():
    """Called by the test connector's scan_inbound. Drains the queue."""
    pending = list(_scan_queue)
    _scan_queue.clear()
    return jsonify(pending)


@app.route('/_set_scan', methods=['POST'])
def set_scan():
    """Test harness: queue an inbound message to be returned on next scan."""
    _scan_queue.append(request.get_json(force=True))
    return '', 204


@app.route('/track/<sid>', methods=['GET'])
def track(sid: str):
    """Called by the test connector's track_outbound for a single SID."""
    return jsonify(_tracked_statuses.get(sid, {}))


@app.route('/_set_track/<sid>', methods=['POST'])
def set_track(sid: str):
    """Test harness: set the current status for an external ID."""
    _tracked_statuses[sid] = request.get_json(force=True)
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
    _scan_queue.clear()
    _tracked_statuses.clear()
    return '', 204


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    app.run(host='0.0.0.0', port=port)
