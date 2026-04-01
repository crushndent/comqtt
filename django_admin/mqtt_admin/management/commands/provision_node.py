from django.core.management.base import BaseCommand, CommandError
from mqtt_admin.node_provisioning import provision_node
from mqtt_admin.models import Node


class Command(BaseCommand):
    help = 'Provision a new node with MQTT user and default ACLs'

    def add_arguments(self, parser):
        parser.add_argument(
            'node_id',
            type=str,
            help='Unique identifier for the node (e.g., MAC address or UUID)'
        )
        parser.add_argument(
            '--name',
            type=str,
            help='Human-readable name for the node'
        )
        parser.add_argument(
            '--location',
            type=str,
            help='Physical location of the node'
        )

    def handle(self, *args, **options):
        node_id = options['node_id']
        node_name = options.get('name')
        location = options.get('location')

        if Node.objects.filter(node_id=node_id).exists():
            raise CommandError(f"Node with ID '{node_id}' already exists.")

        try:
            user = provision_node(node_id, node_name)
            password = user._plain_password

            node = Node.objects.get(node_id=node_id)
            if location:
                node.location = location
                node.save()

            self.stdout.write(self.style.SUCCESS(f"Node '{node_id}' provisioned successfully."))
            self.stdout.write(f"  Username: {user.username}")
            self.stdout.write(f"  Password: {password}")
            self.stdout.write(f"  Node Name: {node.name}")
            if location:
                self.stdout.write(f"  Location: {node.location}")

        except Exception as e:
            raise CommandError(f"Failed to provision node: {e}")
