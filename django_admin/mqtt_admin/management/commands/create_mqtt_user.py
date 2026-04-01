import secrets
import string
from django.core.management.base import BaseCommand, CommandError
from mqtt_admin.models import MqttUser


class Command(BaseCommand):
    help = 'Create an MQTT user with optional password or auto-generated'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='Username for the MQTT user'
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Password for the MQTT user (auto-generated if not provided)'
        )
        parser.add_argument(
            '--allow',
            action='store_true',
            help='Allow the user to connect (default)'
        )
        parser.add_argument(
            '--deny',
            action='store_true',
            help='Deny the user from connecting'
        )

    def handle(self, *args, **options):
        username = options['username']
        password = options.get('password')
        allow = options.get('allow', False)
        deny = options.get('deny', False)

        if MqttUser.objects.filter(username=username).exists():
            raise CommandError(f"MQTT user '{username}' already exists.")

        if not password:
            password = self._generate_password()
            generated = True
        else:
            generated = False

        if deny and allow:
            raise CommandError("Cannot specify both --allow and --deny.")

        allow_value = 0 if deny else 1

        try:
            user = MqttUser(username=username, allow=allow_value)
            user.set_password(password)
            user.save()

            self.stdout.write(self.style.SUCCESS(f"MQTT user '{username}' created successfully."))
            if generated:
                self.stdout.write(f"  Generated Password: {password}")
            self.stdout.write(f"  Access: {'Allowed' if allow_value == 1 else 'Denied'}")

        except Exception as e:
            raise CommandError(f"Failed to create MQTT user: {e}")

    def _generate_password(self, length: int = 16) -> str:
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
