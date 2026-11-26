import base64
from unittest.mock import MagicMock, patch
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from account.models import (
    ActivityAction,
    CustomUser,
    LoginMethod,
    SuperAccessChallenge,
    SuperAccessRateLimit,
    UserActivityLog,
    UserRoles,
    UserSession,
)
from account.serializers import CreateUserSerializer, UpdateUserSerializer
from account.totp import compute_totp, generate_totp_secret, get_totp_uri, verify_totp
from account.views import _get_request_origin, _get_safe_redirect_uri
from info.models import Ministry


class OriginValidationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_get_request_origin_handles_missing_and_invalid_headers(self):
        req_empty = self.factory.get('/api/auth/code')
        self.assertIsNone(_get_request_origin(req_empty))

        req_bad = self.factory.get('/api/auth/code', HTTP_ORIGIN='not-a-url')
        self.assertIsNone(_get_request_origin(req_bad))

    def test_get_request_origin_extracts_scheme_and_netloc_from_referer(self):
        req = self.factory.get('/api/auth/code', HTTP_REFERER='https://xarita.academy.uz/dashboard?foo=1')
        self.assertEqual(_get_request_origin(req), 'https://xarita.academy.uz')

    @override_settings(
        CORS_ALLOWED_ORIGINS=['https://termit.academy.uz'],
        MAP_ORIGIN='https://xarita.academy.uz',
        REDIRECT_URI='https://termit.academy.uz/auth',
    )
    def test_get_safe_redirect_uri_allows_known_origins_and_blocks_unknown(self):
        req_termit = self.factory.get('/api/auth/code', HTTP_ORIGIN='https://termit.academy.uz')
        self.assertEqual(_get_safe_redirect_uri(req_termit), 'https://termit.academy.uz/auth')

        req_xarita = self.factory.get('/api/auth/code', HTTP_ORIGIN='https://xarita.academy.uz')
        self.assertEqual(_get_safe_redirect_uri(req_xarita), 'https://xarita.academy.uz/auth')

        req_evil = self.factory.get('/api/auth/code', HTTP_ORIGIN='https://evil.example.com')
        self.assertEqual(_get_safe_redirect_uri(req_evil), 'https://termit.academy.uz/auth')

        req_none = self.factory.get('/api/auth/code')
        self.assertEqual(_get_safe_redirect_uri(req_none), 'https://termit.academy.uz/auth')


class TotpTests(SimpleTestCase):
    def test_rfc6238_known_vector_and_verification(self):
        # RFC 6238 SHA1 ASCII secret "12345678901234567890" -> 8-digit 94287082 at t=59 => 6-digit 287082
        rfc_secret_b32 = base64.b32encode(b'12345678901234567890').decode('ascii')
        self.assertEqual(compute_totp(rfc_secret_b32, 59 // 30), '287082')

        ok, step = verify_totp(rfc_secret_b32, '287082', valid_window=1, now=59.0)
        self.assertTrue(ok)
        self.assertEqual(step, 1)

        bad, bad_step = verify_totp(rfc_secret_b32, '000000', valid_window=1, now=59.0)
        self.assertFalse(bad)
        self.assertIsNone(bad_step)

    def test_generate_secret_and_uri(self):
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, account_name='admin', issuer='Termit Academy')
        self.assertTrue(uri.startswith('otpauth://totp/'))
        self.assertIn(f'secret={secret}', uri)


class SuperAccessApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create(
            username='test_admin',
            pinfl='12345678901234',
            full_name='Test Admin',
            role=UserRoles.ADMIN,
            is_active=True,
        )
        self.totp_secret = generate_totp_secret()
        self.access_key = 'a' * 64

    @override_settings(ENABLED_SUPER_ACCESS=True, SUPER_ACCESS_KEY='', SUPER_ACCESS_TOTP_SECRET='')
    def test_disabled_when_secrets_missing(self):
        status_res = self.client.get('/api/auth/super-access/status')
        self.assertEqual(status_res.status_code, 404)
        res = self.client.post('/api/auth/super-access/verify', {'key': 'x', 'totp': '123456'}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_disabled_when_flag_is_false_even_with_secrets(self):
        with override_settings(
            ENABLED_SUPER_ACCESS=False,
            SUPER_ACCESS_KEY=self.access_key,
            SUPER_ACCESS_TOTP_SECRET=self.totp_secret,
        ):
            self.assertEqual(self.client.get('/api/auth/super-access/status').status_code, 404)
            self.assertEqual(
                self.client.post('/api/auth/super-access/verify', {'key': self.access_key, 'totp': '123456'}, format='json').status_code,
                404,
            )

    def test_verify_and_single_use_login_with_replay_and_rate_limit(self):
        import time
        step = int(time.time() // 30)
        valid_code = compute_totp(self.totp_secret, step)

        with override_settings(
            ENABLED_SUPER_ACCESS=True,
            SUPER_ACCESS_KEY=self.access_key,
            SUPER_ACCESS_TOTP_SECRET=self.totp_secret,
        ):
            status_res = self.client.get('/api/auth/super-access/status')
            self.assertEqual(status_res.status_code, 200)
            self.assertEqual(status_res.data, {'enabled': True, 'local': False, 'totp_required': True})
            # Wrong TOTP fails with 403
            bad = self.client.post(
                '/api/auth/super-access/verify',
                {'key': self.access_key, 'totp': '000000'},
                format='json',
                HTTP_X_REAL_IP='10.0.0.5',
            )
            self.assertEqual(bad.status_code, 403)

            # Correct key + TOTP succeeds
            ok = self.client.post(
                '/api/auth/super-access/verify',
                {'key': self.access_key, 'totp': valid_code},
                format='json',
                HTTP_X_REAL_IP='10.0.0.5',
            )
            self.assertEqual(ok.status_code, 200)
            self.assertTrue(ok.data['success'])
            self.assertIn('challenge_token', ok.data)
            self.assertNotIn('pinfl', ok.data['users'][0])
            token = ok.data['challenge_token']

            # Replaying the same TOTP step is blocked
            replay = self.client.post(
                '/api/auth/super-access/verify',
                {'key': self.access_key, 'totp': valid_code},
                format='json',
                HTTP_X_REAL_IP='10.0.0.5',
            )
            self.assertEqual(replay.status_code, 403)

            # Login from different IP fails
            wrong_ip = self.client.post(
                '/api/auth/super-access/login',
                {'challenge_token': token, 'user_id': self.user.id},
                format='json',
                HTTP_X_REAL_IP='10.0.0.9',
            )
            self.assertEqual(wrong_ip.status_code, 403)

            # Login from matching IP succeeds and sets auth cookies
            login_ok = self.client.post(
                '/api/auth/super-access/login',
                {'challenge_token': token, 'user_id': self.user.id},
                format='json',
                HTTP_X_REAL_IP='10.0.0.5',
            )
            self.assertEqual(login_ok.status_code, 200)
            self.assertIn('access', login_ok.cookies)
            self.assertIn('refresh', login_ok.cookies)

            # Reusing challenge_token fails
            reuse = self.client.post(
                '/api/auth/super-access/login',
                {'challenge_token': token, 'user_id': self.user.id},
                format='json',
                HTTP_X_REAL_IP='10.0.0.5',
            )
            self.assertEqual(reuse.status_code, 403)

            # 5 failed attempts trigger 429 lockout
            for _ in range(5):
                self.client.post(
                    '/api/auth/super-access/verify',
                    {'key': 'wrong', 'totp': '000000'},
                    format='json',
                    HTTP_X_REAL_IP='10.0.0.77',
                )
            locked = self.client.post(
                '/api/auth/super-access/verify',
                {'key': self.access_key, 'totp': valid_code},
                format='json',
                HTTP_X_REAL_IP='10.0.0.77',
            )
            self.assertEqual(locked.status_code, 429)

    def test_local_mode_skips_key_and_totp_only_when_debug_and_enabled(self):
        # Safety: LOCAL=True must not bypass 2FA when DEBUG=False
        with override_settings(
            ENABLED_SUPER_ACCESS=True,
            LOCAL=True,
            DEBUG=False,
            SUPER_ACCESS_KEY=self.access_key,
            SUPER_ACCESS_TOTP_SECRET=self.totp_secret,
        ):
            res = self.client.get('/api/auth/super-access/status')
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data, {'enabled': True, 'local': False, 'totp_required': True})

        # Disabled when ENABLED_SUPER_ACCESS=False even if LOCAL=True and DEBUG=True
        with override_settings(ENABLED_SUPER_ACCESS=False, LOCAL=True, DEBUG=True):
            self.assertEqual(self.client.get('/api/auth/super-access/status').status_code, 404)

        # Enabled + LOCAL=True + DEBUG=True skips key/TOTP even without secrets configured
        with override_settings(
            ENABLED_SUPER_ACCESS=True,
            LOCAL=True,
            DEBUG=True,
            SUPER_ACCESS_KEY='',
            SUPER_ACCESS_TOTP_SECRET='',
        ):
            status_res = self.client.get('/api/auth/super-access/status', HTTP_X_REAL_IP='127.0.0.1')
            self.assertEqual(status_res.status_code, 200)
            self.assertTrue(status_res.data['enabled'])
            self.assertTrue(status_res.data['local'])
            self.assertIn('challenge_token', status_res.data)
            self.assertTrue(len(status_res.data['users']) >= 1)

            login_res = self.client.post(
                '/api/auth/super-access/login',
                {'challenge_token': status_res.data['challenge_token'], 'user_id': self.user.id},
                format='json',
                HTTP_X_REAL_IP='127.0.0.1',
            )
            self.assertEqual(login_res.status_code, 200)
            self.assertIn('access', login_res.cookies)

    def test_map_origin_only_allows_me_users_in_super_access(self):
        me_user = CustomUser.objects.create(
            username='test_me',
            pinfl='55555555555555',
            full_name='Ministry User',
            role=UserRoles.ME,
            is_active=True,
        )
        with override_settings(
            ENABLED_SUPER_ACCESS=True,
            LOCAL=True,
            DEBUG=True,
            MAP_ORIGIN='http://xarita.localhost:5173',
        ):
            status_res = self.client.get(
                '/api/auth/super-access/status',
                HTTP_ORIGIN='http://xarita.localhost:5173',
                HTTP_X_REAL_IP='127.0.0.1',
            )
            self.assertEqual(status_res.status_code, 200)
            returned_ids = [u['id'] for u in status_res.data['users']]
            self.assertEqual(returned_ids, [me_user.id])

            # Non-ME user is rejected on MAP_ORIGIN
            denied = self.client.post(
                '/api/auth/super-access/login',
                {'challenge_token': status_res.data['challenge_token'], 'user_id': self.user.id},
                format='json',
                HTTP_ORIGIN='http://xarita.localhost:5173',
                HTTP_X_REAL_IP='127.0.0.1',
            )
            self.assertEqual(denied.status_code, 403)

            # ME user succeeds on MAP_ORIGIN
            allowed = self.client.post(
                '/api/auth/super-access/login',
                {'challenge_token': status_res.data['challenge_token'], 'user_id': me_user.id},
                format='json',
                HTTP_ORIGIN='http://xarita.localhost:5173',
                HTTP_X_REAL_IP='127.0.0.1',
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertIn('access', allowed.cookies)

    def test_verify_and_login_without_totp_when_totp_secret_empty(self):
        with override_settings(
            ENABLED_SUPER_ACCESS=True,
            LOCAL=False,
            DEBUG=False,
            SUPER_ACCESS_KEY=self.access_key,
            SUPER_ACCESS_TOTP_SECRET='',
        ):
            status_res = self.client.get('/api/auth/super-access/status')
            self.assertEqual(status_res.status_code, 200)
            self.assertEqual(status_res.data, {'enabled': True, 'local': False, 'totp_required': False})

            bad_key = self.client.post(
                '/api/auth/super-access/verify',
                {'key': 'wrong-key'},
                format='json',
                HTTP_X_REAL_IP='10.0.0.12',
            )
            self.assertEqual(bad_key.status_code, 403)

            ok = self.client.post(
                '/api/auth/super-access/verify',
                {'key': self.access_key},
                format='json',
                HTTP_X_REAL_IP='10.0.0.12',
            )
            self.assertEqual(ok.status_code, 200)
            self.assertTrue(ok.data['success'])
            token = ok.data['challenge_token']

            login_ok = self.client.post(
                '/api/auth/super-access/login',
                {'challenge_token': token, 'user_id': self.user.id},
                format='json',
                HTTP_X_REAL_IP='10.0.0.12',
            )
            self.assertEqual(login_ok.status_code, 200)
            self.assertIn('access', login_ok.cookies)
            self.assertIn('refresh', login_ok.cookies)


class UserSerializerTests(TestCase):
    def test_create_and_update_user_serializers_persist_full_name(self):
        ministry = Ministry.objects.create(name='Test Vazirlik')
        create_ser = CreateUserSerializer(data={
            'full_name': 'ALI VALIYEV',
            'pinfl': '44444444444444',
            'role': UserRoles.ME,
            'ministry': ministry.id,
            'regions': [],
        })
        self.assertTrue(create_ser.is_valid(), create_ser.errors)
        user = create_ser.save()
        self.assertEqual(user.full_name, 'ALI VALIYEV')

        update_ser = UpdateUserSerializer(
            instance=user,
            data={
                'full_name': 'ALI VALIYEV UPDATED',
                'role': UserRoles.ME,
                'ministry': ministry.id,
                'regions': [],
            },
        )
        self.assertTrue(update_ser.is_valid(), update_ser.errors)
        updated = update_ser.save()
        self.assertEqual(updated.full_name, 'ALI VALIYEV UPDATED')


class ActivityLogTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = CustomUser.objects.create(
            username='log_admin',
            pinfl='11112222333344',
            full_name='Activity Admin',
            role=UserRoles.ADMIN,
            is_active=True,
        )
        self.rm_user = CustomUser.objects.create(
            username='log_rm',
            pinfl='99998888777766',
            full_name='Regional Staff',
            role=UserRoles.RM,
            is_active=True,
        )

    def test_super_access_login_navigation_action_and_logout_lifecycle(self):
        with override_settings(ENABLED_SUPER_ACCESS=True, LOCAL=True, DEBUG=True):
            status_res = self.client.get('/api/auth/super-access/status', HTTP_X_REAL_IP='10.1.2.3')
            self.assertEqual(status_res.status_code, 200)
            token = status_res.data['challenge_token']

            login_res = self.client.post(
                '/api/auth/super-access/login',
                {'challenge_token': token, 'user_id': self.admin_user.id},
                format='json',
                HTTP_X_REAL_IP='10.1.2.3',
            )
            self.assertEqual(login_res.status_code, 200)

        session = UserSession.objects.get(user=self.admin_user)
        self.assertTrue(session.is_active)
        self.assertIsNone(session.logout_at)
        self.assertEqual(session.login_method, LoginMethod.SUPER_ACCESS)
        self.assertEqual(session.ip_address, '10.1.2.3')

        login_log = UserActivityLog.objects.filter(user=self.admin_user, action=ActivityAction.LOGIN).first()
        self.assertIsNotNone(login_log)
        self.assertEqual(login_log.session_id, session.id)
        self.assertEqual(login_log.from_page, '/auth/super-access')

        # Track page navigation
        nav_res = self.client.post(
            '/api/activity-logs/navigate',
            {'from_page': '/dashboard', 'to_page': '/users', 'page_title': 'Users'},
            format='json',
            HTTP_X_REAL_IP='10.1.2.3',
        )
        self.assertEqual(nav_res.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.last_page, '/users')

        nav_log = UserActivityLog.objects.filter(user=self.admin_user, action=ActivityAction.PAGE_VIEW).first()
        self.assertIsNotNone(nav_log)
        self.assertEqual(nav_log.from_page, '/dashboard')
        self.assertEqual(nav_log.to_page, '/users')
        self.assertEqual(nav_log.session_id, session.id)

        # Mutating API action with X-Current-Page header is logged automatically by middleware
        ministry_res = self.client.post(
            '/api/info/ministries',
            {'name': 'Audit Test Ministry'},
            format='json',
            HTTP_X_CURRENT_PAGE='/ministries',
            HTTP_X_REAL_IP='10.1.2.3',
        )
        self.assertEqual(ministry_res.status_code, 201)

        ministry_id = ministry_res.data['id']
        action_log = UserActivityLog.objects.filter(
            user=self.admin_user, action=ActivityAction.CREATE, resource_type='ministry'
        ).first()
        self.assertIsNotNone(action_log)
        self.assertEqual(action_log.from_page, '/ministries')
        self.assertEqual(action_log.method, 'POST')
        self.assertEqual(action_log.session_id, session.id)
        self.assertEqual(action_log.resource_id, str(ministry_id))
        self.assertEqual(action_log.object_repr, 'Audit Test Ministry')
        self.assertEqual(action_log.changes.get('schema'), 'audit-diff/v1')
        self.assertEqual(action_log.changes.get('operation'), 'create')
        self.assertEqual(action_log.changes.get('model'), 'info.Ministry')
        self.assertEqual(
            action_log.changes.get('fields', {}).get('name'),
            {'old': None, 'new': 'Audit Test Ministry'},
        )
        self.assertEqual(
            action_log.changes.get('request_payload'),
            {'name': 'Audit Test Ministry'},
        )

        # PUT update captures field-level old -> new diff in standard JSON format
        update_res = self.client.put(
            f'/api/info/ministries/{ministry_id}',
            {'name': 'Renamed Audit Ministry'},
            format='json',
            HTTP_X_CURRENT_PAGE='/ministries',
            HTTP_X_REAL_IP='10.1.2.3',
        )
        self.assertEqual(update_res.status_code, 200)

        update_log = UserActivityLog.objects.filter(
            user=self.admin_user, action=ActivityAction.UPDATE, resource_type='ministry'
        ).first()
        self.assertIsNotNone(update_log)
        self.assertEqual(update_log.changes.get('operation'), 'update')
        self.assertEqual(
            update_log.changes.get('fields', {}).get('name'),
            {'old': 'Audit Test Ministry', 'new': 'Renamed Audit Ministry'},
        )

        # Admin can query activity logs, sessions, and summary
        logs_res = self.client.get('/api/activity-logs')
        self.assertEqual(logs_res.status_code, 200)
        self.assertGreaterEqual(logs_res.data['count'], 4)
        first_row = logs_res.data['results'][0]
        self.assertIn('login_at', first_row)
        self.assertIn('logout_at', first_row)
        self.assertIn('from_page', first_row)
        self.assertIn('to_page', first_row)
        self.assertIn('changes', first_row)
        self.assertIn('object_repr', first_row)

        sessions_res = self.client.get('/api/activity-logs/sessions')
        self.assertEqual(sessions_res.status_code, 200)
        self.assertEqual(sessions_res.data['count'], 1)
        self.assertEqual(sessions_res.data['results'][0]['actions_count'], 4)

        summary_res = self.client.get('/api/activity-logs/summary')
        self.assertEqual(summary_res.status_code, 200)
        self.assertEqual(summary_res.data['active_sessions'], 1)
        self.assertGreaterEqual(summary_res.data['today_logins'], 1)

        # Logout closes session and logs logout_at + from_page
        logout_res = self.client.post(
            '/api/auth/logout',
            {'current_page': '/ministries'},
            format='json',
            HTTP_X_REAL_IP='10.1.2.3',
        )
        self.assertEqual(logout_res.status_code, 200)

        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertIsNotNone(session.logout_at)
        self.assertEqual(session.logout_reason, 'manual')

        logout_log = UserActivityLog.objects.filter(user=self.admin_user, action=ActivityAction.LOGOUT).first()
        self.assertIsNotNone(logout_log)
        self.assertEqual(logout_log.from_page, '/ministries')
        self.assertEqual(logout_log.to_page, '/auth')
        self.assertEqual(logout_log.session_id, session.id)

    def test_activity_log_endpoints_require_admin_or_cd_role(self):
        unauth_res = self.client.get('/api/activity-logs')
        self.assertEqual(unauth_res.status_code, 401)

        self.client.force_authenticate(user=self.rm_user)
        self.assertEqual(self.client.get('/api/activity-logs').status_code, 403)
        self.assertEqual(self.client.get('/api/activity-logs/sessions').status_code, 403)
        self.assertEqual(self.client.get('/api/activity-logs/summary').status_code, 403)

        cd_user = CustomUser.objects.create(
            username='log_cd',
            pinfl='77776666555544',
            full_name='Center Director',
            role=UserRoles.CD,
            is_active=True,
        )
        self.client.force_authenticate(user=cd_user)
        self.assertEqual(self.client.get('/api/activity-logs').status_code, 200)
        self.assertEqual(self.client.get('/api/activity-logs/sessions').status_code, 200)
        self.assertEqual(self.client.get('/api/activity-logs/summary').status_code, 200)

    @patch('account.views.requests.post')
    def test_oneid_login_creates_session_and_login_log(self, mock_post):
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {'access_token': 'oneid-access'}

        profile_resp = MagicMock()
        profile_resp.status_code = 200
        profile_resp.json.return_value = {
            'pin': self.rm_user.pinfl,
            'auth_method': 'PKCMETHOD',
            'first_name': 'Regional',
            'sur_name': 'Staff',
        }
        mock_post.side_effect = [token_resp, profile_resp]

        res = self.client.get('/api/auth/login', {'code': 'dummy-code'}, HTTP_X_REAL_IP='10.9.8.7')
        self.assertEqual(res.status_code, 200)
        self.assertIn('access', res.cookies)

        session = UserSession.objects.get(user=self.rm_user)
        self.assertEqual(session.login_method, LoginMethod.ONE_ID)
        self.assertEqual(session.ip_address, '10.9.8.7')
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.rm_user, session=session, action=ActivityAction.LOGIN
            ).exists()
        )
