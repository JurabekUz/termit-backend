import secrets

from django.core.management.base import BaseCommand

from account.totp import generate_totp_secret, get_totp_uri


class Command(BaseCommand):
    help = 'Generate a new SUPER_ACCESS_KEY and Google Authenticator TOTP secret for .env'

    def add_arguments(self, parser):
        parser.add_argument('--issuer', default='Termit Academy', help='Issuer shown in Google Authenticator')
        parser.add_argument('--account', default='super-access', help='Account label shown in Google Authenticator')

    def handle(self, *args, **options):
        key = secrets.token_hex(32)
        totp_secret = generate_totp_secret()
        uri = get_totp_uri(totp_secret, account_name=options['account'], issuer=options['issuer'])

        self.stdout.write(self.style.SUCCESS('\nAdd these lines to backend/.env:\n'))
        self.stdout.write('ENABLED_SUPER_ACCESS=True')
        self.stdout.write(f'SUPER_ACCESS_KEY={key}')
        self.stdout.write(f'SUPER_ACCESS_TOTP_SECRET={totp_secret}\n')
        self.stdout.write('Google Authenticator manual setup key (Time-based / 6 digits / 30s):')
        self.stdout.write(f'  {totp_secret}\n')
        self.stdout.write('Or otpauth URI (for QR code generation):')
        self.stdout.write(f'  {uri}\n')
