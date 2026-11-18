import base64
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from account.models import CustomUser, SuperAccessChallenge, SuperAccessRateLimit, UserRoles
from account.totp import compute_totp, generate_totp_secret, get_totp_uri, verify_totp
from account.views import _get_request_origin, _get_safe_redirect_uri


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
            self.assertEqual(status_res.data, {'enabled': True})
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
