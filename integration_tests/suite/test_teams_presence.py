# Copyright 2022-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from contextlib import contextmanager
from datetime import datetime, timedelta
from uuid import uuid4

import requests
from hamcrest import (
    assert_that,
    contains_exactly,
    contains_inanyorder,
    has_entries,
    has_entry,
    has_items,
    has_properties,
    starts_with,
)

from .helpers import fixtures
from .helpers.base import TeamsIntegrationTest, use_asset


@use_asset('teams')
class TestTeams(TeamsIntegrationTest):
    def setUp(self):
        self.confd.set_ingresses('chatd:9304')
        super().setUp()

    @fixtures.db.user()
    def test_validation_token_when_user_is_connected(self, user):
        url = self._user_notification_url(user)
        validation_token = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

        with self._connect_user(user):
            response = requests.post(url, params={'validationToken': validation_token})

        assert_that(
            response,
            has_properties(
                status_code=200,
                headers=has_entry('Content-Type', starts_with('text/plain')),
                content=validation_token.encode(),
            ),
        )

    @fixtures.db.user()
    def test_validation_token_when_user_is_not_connected(self, user):
        url = self._user_notification_url(user)
        validation_token = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

        response = requests.post(url, params={'validationToken': validation_token})
        assert_that(response, has_properties(status_code=404))

    @fixtures.db.user()
    def test_update_return_404_when_user_is_not_connected(self, user):
        url = self._user_notification_url(user)
        expiration = (
            (datetime.now() + timedelta(seconds=60)).isoformat().replace('+00:00', 'Z')
        )
        bogus_data = {
            'value': [
                {
                    'subscriptionId': str(uuid4()),
                    'subscriptionExpirationDateTime': expiration,
                    'changeType': 'updated',
                    'clientState': 'some-state',
                    'resource': f'/communications/presences/{uuid4()}',
                    'resourceData': {
                        'availability': '',
                        'activity': 'currently doing something',
                    },
                }
            ]
        }

        response = requests.post(url, json=bogus_data)
        assert_that(response, has_properties(status_code=404))

    @fixtures.db.user()
    def test_presence_update_returns_400_on_invalid_data_when_user_is_connected(
        self, user
    ):
        url = self._user_notification_url(user)
        expiration = (
            (datetime.now() + timedelta(seconds=60)).isoformat().replace('+00:00', 'Z')
        )
        bogus_data = {
            'value': [
                {
                    'subscriptionId': str(uuid4()),
                    'subscriptionExpirationDateTime': expiration,
                    'changeType': 'updated',
                    'clientState': 'some-state',
                    'resource': f'/communications/presences/{uuid4()}',
                    'resourceData': {
                        'availability': '',
                        'activity': 'currently doing something',
                    },
                }
            ]
        }

        with self._connect_user(user):
            response = requests.post(url, json=bogus_data)

        assert_that(response, has_properties(status_code=400))
        assert_that(
            response.json(),
            has_entries(error_id='invalid-data', message='Sent data is invalid'),
        )

    @fixtures.db.user()
    def test_that_empty_body_for_post_teams_presence_returns_400(self, user):
        with self._connect_user(user):
            self.assert_empty_body_returns_400(
                [('post', f'users/{user.uuid}/teams/presence')]
            )

    @fixtures.db.user(state='available')
    def test_dont_synchronize_when_user_is_not_connected(self, user):
        response = self.microsoft.set_presence(user.uuid, 'Away')
        assert_that(response, has_properties(status_code=404))

    @fixtures.db.user(state='available')
    def test_synchronize_presence_when_user_connected(self, user):
        accumulator = self.bus.accumulator(headers={'name': 'chatd_presence_updated'})

        with self._connect_user(user):
            self.microsoft.set_presence(user.uuid, 'Away')

        assert_that(
            accumulator.accumulate(with_headers=False),
            has_items(
                has_entries(
                    data=has_entries(state='away'),
                )
            ),
        )

    @fixtures.db.user(state='available')
    def test_presence_map_teams_to_wazo(self, user):
        teams_presences = (
            'Available',
            'AvailableIdle',
            'Away',
            'BeRightBack',
            'Busy',
            'BusyIdle',
            'DoNotDisturb',
            'Offline',
            'PresenceUnknown',
        )
        accumulator = self.bus.accumulator(headers={'name': 'chatd_presence_updated'})

        with self._connect_user(user):
            for state in teams_presences:
                self.microsoft.set_presence(user.uuid, state)

        assert_that(
            accumulator.accumulate(),
            contains_exactly(
                has_entries(
                    # Available -> available
                    data=has_entries(state='available'),
                ),
                has_entries(
                    # AvailableIdle -> available
                    data=has_entries(state='available'),
                ),
                has_entries(
                    # Away -> away
                    data=has_entries(state='away'),
                ),
                has_entries(
                    # BeRightBack -> away
                    data=has_entries(state='away'),
                ),
                has_entries(
                    # Busy -> unavailable
                    data=has_entries(state='unavailable'),
                ),
                has_entries(
                    # BusyIdle -> unavailable
                    data=has_entries(state='unavailable'),
                ),
                has_entries(
                    # DoNotDisturb -> unavailable
                    data=has_entries(state='unavailable'),
                ),
            ),
        )

    @fixtures.db.user(state='available')
    def test_presence_enable_dnd(self, user):
        accumulator = self.bus.accumulator(headers={'name': 'chatd_presence_updated'})

        with self._connect_user(user):
            self.microsoft.set_presence(user.uuid, 'Busy')

        assert_that(
            accumulator.accumulate(with_headers=True),
            contains_exactly(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            uuid=str(user.uuid),
                            state='unavailable',
                            do_not_disturb=True,
                        )
                    )
                )
            ),
        )

    @fixtures.db.user(state='unavailable')
    def test_presence_disable_dnd(self, user):
        accumulator = self.bus.accumulator(headers={'name': 'chatd_presence_updated'})

        with self._connect_user(user):
            self.microsoft.set_presence(user.uuid, 'Available')

        assert_that(
            accumulator.accumulate(with_headers=True),
            contains_exactly(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            uuid=str(user.uuid),
                            state='available',
                            do_not_disturb=False,
                        )
                    )
                )
            ),
        )

    @fixtures.db.user(state='available')
    @fixtures.db.user(state='away')
    def test_presence_multiple_users(self, user1, user2):
        accumulator = self.bus.accumulator(headers={'name': 'chatd_presence_updated'})

        with self._connect_user(user1), self._connect_user(user2):
            self.microsoft.set_presence(user1.uuid, 'Busy')
            self.microsoft.set_presence(user2.uuid, 'Away')
            self.microsoft.set_presence(user1.uuid, 'Available')

        assert_that(
            accumulator.accumulate(with_headers=True),
            contains_exactly(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            uuid=str(user1.uuid),
                            state='unavailable',
                            do_not_disturb=True,
                        )
                    )
                ),
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            uuid=str(user2.uuid),
                            state='away',
                            do_not_disturb=False,
                        )
                    )
                ),
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            uuid=str(user1.uuid),
                            state='available',
                            do_not_disturb=False,
                        )
                    )
                ),
            ),
        )

    @fixtures.db.user()
    def test_start_presence_synchronization_on_chatd_restart(self, user1):
        accumulator = self.bus.accumulator(
            headers={'name': 'user_teams_presence_synchronization_started'}
        )
        self.auth.set_external_users({'microsoft': [{'uuid': str(user1.uuid)}]})
        token = self.microsoft.register_user(uuid4())
        self.auth.set_external_auth(token)

        self.restart_chatd_service()
        self.asset_cls.wait_strategy.wait(self)
        # self.reset_clients()

        assert_that(
            accumulator.accumulate(with_headers=True),
            contains_inanyorder(
                has_entries(
                    message=has_entries(
                        data=has_entries(user_uuid=str(user1.uuid)),
                    )
                )
            ),
        )

    def _assert_event_received(self, accumulator, user_uuid):
        assert_that(
            accumulator.accumulate(with_headers=True),
            has_items(
                has_entries(
                    message=has_entries(
                        data=has_entry('user_uuid', str(user_uuid)),
                    )
                )
            ),
        )

    @contextmanager
    def _connect_user(self, user):
        start_events = self.bus.accumulator(
            headers={'name': 'user_teams_presence_synchronization_started'}
        )
        stop_events = self.bus.accumulator(
            headers={'name': 'user_teams_presence_synchronization_stopped'}
        )

        token = self.microsoft.register_user(user.uuid)
        self.auth.set_external_auth(token)

        self.bus.send_external_auth_added_event(
            user.tenant_uuid, user.uuid, 'microsoft'
        )

        try:
            self._assert_event_received(start_events, user.uuid)
            yield
        finally:
            self.bus.send_external_auth_deleted_event(
                user.tenant_uuid, user.uuid, 'microsoft'
            )
            self._assert_event_received(stop_events, user.uuid)
            self.microsoft.unregister_user(user.uuid).raise_for_status()

    def _user_notification_url(self, user):
        port = self.asset_cls.service_port(9304, 'chatd')
        return f'http://127.0.0.1:{port}/1.0/users/{user.uuid}/teams/presence'
