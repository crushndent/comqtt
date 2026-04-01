from django.core.management.base import BaseCommand, CommandError
from mqtt_admin.models import MqttUser, MqttAcl


class Command(BaseCommand):
    help = 'Add ACL entry for an existing MQTT user'

    ACCESS_LEVELS = {
        'deny': 0,
        'write': 1,
        'read': 2,
        'readwrite': 3,
    }

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='Username of the MQTT user'
        )
        parser.add_argument(
            'topic',
            type=str,
            help='MQTT topic pattern'
        )
        parser.add_argument(
            '--access',
            type=str,
            default='readwrite',
            choices=list(self.ACCESS_LEVELS.keys()),
            help='Access level for the topic (default: readwrite)'
        )

    def handle(self, *args, **options):
        username = options['username']
        topic = options['topic']
        access = options['access']

        if not MqttUser.objects.filter(username=username).exists():
            raise CommandError(f"MQTT user '{username}' does not exist.")

        access_value = self.ACCESS_LEVELS[access]
        access_display = dict(MqttAcl.ACCESS_CHOICES)[access_value]

        if MqttAcl.objects.filter(username=username, topic=topic).exists():
            raise CommandError(f"ACL entry for user '{username}' on topic '{topic}' already exists.")

        try:
            acl = MqttAcl.objects.create(
                username=username,
                topic=topic,
                access=access_value
            )

            self.stdout.write(self.style.SUCCESS(f"ACL entry created successfully."))
            self.stdout.write(f"  User: {acl.username}")
            self.stdout.write(f"  Topic: {acl.topic}")
            self.stdout.write(f"  Access: {access_display}")

        except Exception as e:
            raise CommandError(f"Failed to add ACL entry: {e}")
