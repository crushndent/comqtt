import csv
from django.core.management.base import BaseCommand, CommandError
from mqtt_admin.node_provisioning import provision_node
from mqtt_admin.models import Node


class Command(BaseCommand):
    help = 'Import nodes from a CSV file (node_id,name,location)'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the CSV file containing node data'
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip existing nodes instead of failing'
        )

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        skip_existing = options.get('skip_existing', False)

        try:
            with open(csv_file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f"File '{csv_file_path}' not found.")
        except Exception as e:
            raise CommandError(f"Failed to read CSV file: {e}")

        if not rows:
            self.stdout.write(self.style.WARNING("CSV file is empty."))
            return

        created_count = 0
        skipped_count = 0
        error_count = 0
        credentials = []

        for i, row in enumerate(rows, 1):
            if len(row) < 1:
                self.stderr.write(self.style.WARNING(f"Row {i}: Empty row, skipping."))
                continue

            node_id = row[0].strip()
            node_name = row[1].strip() if len(row) > 1 else None
            location = row[2].strip() if len(row) > 2 else None

            if not node_id:
                self.stderr.write(self.style.WARNING(f"Row {i}: Empty node_id, skipping."))
                error_count += 1
                continue

            if Node.objects.filter(node_id=node_id).exists():
                if skip_existing:
                    self.stdout.write(f"Row {i}: Node '{node_id}' already exists, skipping.")
                    skipped_count += 1
                    continue
                else:
                    self.stderr.write(self.style.ERROR(f"Row {i}: Node '{node_id}' already exists."))
                    error_count += 1
                    continue

            try:
                user = provision_node(node_id, node_name)
                password = user._plain_password

                node = Node.objects.get(node_id=node_id)
                if location:
                    node.location = location
                    node.save()

                created_count += 1
                credentials.append({
                    'node_id': node_id,
                    'username': user.username,
                    'password': password,
                    'name': node.name,
                    'location': node.location
                })

                self.stdout.write(f"Row {i}: Node '{node_id}' provisioned successfully.")

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Row {i}: Failed to provision node '{node_id}': {e}"))
                error_count += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Import complete: {created_count} created, {skipped_count} skipped, {error_count} errors."))

        if credentials:
            self.stdout.write("")
            self.stdout.write("Generated Credentials:")
            self.stdout.write("-" * 80)
            self.stdout.write(f"{'Node ID':<20} {'Username':<20} {'Password':<20}")
            self.stdout.write("-" * 80)
            for cred in credentials:
                self.stdout.write(f"{cred['node_id']:<20} {cred['username']:<20} {cred['password']:<20}")
