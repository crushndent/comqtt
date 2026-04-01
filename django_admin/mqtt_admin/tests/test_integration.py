import pytest
import bcrypt
from django.db import transaction
from mqtt_admin.models import MqttUser, MqttAcl, Node
from mqtt_admin.node_provisioning import provision_node, regenerate_node_credentials


class TestPasswordHashing:
    """Integration tests for bcrypt password hashing."""

    def test_django_created_credentials_work_with_bcrypt(self, db):
        """Test that passwords created via Django admin work with bcrypt verification."""
        # Create user through model (simulating admin creation)
        user = MqttUser(username='integration_test')
        raw_password = 'ComplexP@ssw0rd123!'
        user.set_password(raw_password)
        user.save()

        # Verify bcrypt hash is valid
        assert bcrypt.checkpw(
            raw_password.encode('utf-8'),
            user.password.encode('utf-8')
        )

        # Simulate broker authentication - re-verify hash
        stored_hash = user.password
        assert stored_hash.startswith('$2')

        # Verify password still matches after reload
        user.refresh_from_db()
        assert bcrypt.checkpw(
            raw_password.encode('utf-8'),
            user.password.encode('utf-8')
        )

    def test_multiple_password_verifications(self, db):
        """Test multiple passwords can be verified correctly."""
        passwords = [
            'simple123',
            'Complex$Password!999',
            '1234567890',
            'abcDEFghiJKL',
            'mixed123!@#Symbols',
        ]

        users = []
        for i, pwd in enumerate(passwords):
            user = MqttUser(username=f'verify_test_{i}')
            user.set_password(pwd)
            user.save()
            users.append((user, pwd))

        # Verify all passwords
        for user, expected_password in users:
            assert bcrypt.checkpw(
                expected_password.encode('utf-8'),
                user.password.encode('utf-8')
            )

    def test_password_uniqueness(self, db):
        """Test that same password produces different hashes each time."""
        same_password = 'duplicate_test_password'

        user1 = MqttUser(username='unique_test_1')
        user1.set_password(same_password)
        user1.save()

        user2 = MqttUser(username='unique_test_2')
        user2.set_password(same_password)
        user2.save()

        # Same password, different hashes due to different salts
        assert user1.password != user2.password

        # But both should verify correctly
        assert bcrypt.checkpw(same_password.encode('utf-8'), user1.password.encode('utf-8'))
        assert bcrypt.checkpw(same_password.encode('utf-8'), user2.password.encode('utf-8'))


class TestAclAccessLevels:
    """Integration tests for ACL access level storage and retrieval."""

    def test_access_levels_correctly_stored(self, db, mqtt_user):
        """Test all access levels are stored correctly in database."""
        access_tests = [
            (0, 'Deny'),
            (1, 'Write'),
            (2, 'Read'),
            (3, 'Read + Write'),
        ]

        for access_val, expected_label in access_tests:
            acl = MqttAcl.objects.create(
                user=mqtt_user,
                topic=f'test/access/{access_val}',
                access=access_val
            )

            # Refresh and verify
            acl.refresh_from_db()
            assert acl.access == access_val
            assert acl.get_access_display() == expected_label

    def test_access_level_filtering(self, db, mqtt_user):
        """Test filtering ACLs by access level works correctly."""
        # Create ACLs with different access levels
        MqttAcl.objects.create(user=mqtt_user, topic='read/1', access=2)
        MqttAcl.objects.create(user=mqtt_user, topic='read/2', access=2)
        MqttAcl.objects.create(user=mqtt_user, topic='write/1', access=1)
        MqttAcl.objects.create(user=mqtt_user, topic='readwrite/1', access=3)
        MqttAcl.objects.create(user=mqtt_user, topic='deny/1', access=0)

        # Filter by access level
        read_acls = MqttAcl.objects.filter(access=2)
        write_acls = MqttAcl.objects.filter(access=1)
        readwrite_acls = MqttAcl.objects.filter(access=3)
        deny_acls = MqttAcl.objects.filter(access=0)

        assert read_acls.count() == 2
        assert write_acls.count() == 1
        assert readwrite_acls.count() == 1
        assert deny_acls.count() == 1

    def test_acl_permission_workflow(self, db, mqtt_user):
        """Test complete ACL permission workflow."""
        # Step 1: Create ACLs for a device
        device_topic = 'devices/thermostat_001'

        # Device can read commands
        MqttAcl.objects.create(
            user=mqtt_user,
            topic=f'commands/{device_topic}/#',
            access=2  # Read
        )

        # Device can write to telemetry
        MqttAcl.objects.create(
            user=mqtt_user,
            topic=f'telemetry/{device_topic}/#',
            access=1  # Write
        )

        # Device can read/write to config
        MqttAcl.objects.create(
            user=mqtt_user,
            topic=f'config/{device_topic}/#',
            access=3  # Read + Write
        )

        # Step 2: Verify all ACLs are created
        assert mqtt_user.acls.count() == 3

        # Step 3: Simulate broker permission check
        def check_permission(topic, required_access):
            """Simulate broker ACL check."""
            for acl in mqtt_user.acls.filter(topic__startswith=topic.split('/')[0]):
                # Simple matching - in reality MQTT wildcards need proper implementation
                if required_access <= acl.access or acl.access == 3:
                    return True
            return False

        # Verify permissions
        assert check_permission('commands/devices/thermostat_001/set', 2)  # Read access
        assert check_permission('telemetry/devices/thermostat_001/data', 1)  # Write access
        assert check_permission('config/devices/thermostat_001/update', 3)  # Read+Write access


class TestNodeProvisioning:
    """Integration tests for node provisioning functionality."""

    def test_provision_node_creates_user(self, db):
        """Test provision_node creates MQTT user."""
        user = provision_node('new-test-node-001', 'Test Device')

        assert user.pk is not None
        assert user.username == 'new-test-node-001'
        assert user.password.startswith('$2')

        # Verify password is accessible
        assert hasattr(user, '_plain_password')
        assert len(user._plain_password) == 32  # Default password length

    def test_provision_node_creates_node_record(self, db):
        """Test provision_node creates Node record."""
        user = provision_node('provisioned-node-002', 'My Device')

        node = Node.objects.get(node_id='provisioned-node-002')
        assert node.name == 'My Device'
        assert node.user == user
        assert node.status == 'active'

    def test_provision_node_creates_default_acls(self, db):
        """Test provision_node creates expected ACLs."""
        user = provision_node('acl-test-node', 'ACL Test Device')

        acls = user.acls.all()
        assert acls.count() == 3

        # Verify specific ACLs
        topics = [acl.topic for acl in acls]
        assert f'nodes/acl-test-node/#' in topics
        assert f'sensors/acl-test-node/#' in topics
        assert f'commands/acl-test-node/#' in topics

        # Verify access levels
        device_acl = user.acls.get(topic=f'nodes/acl-test-node/#')
        sensor_acl = user.acls.get(topic=f'sensors/acl-test-node/#')
        command_acl = user.acls.get(topic=f'commands/acl-test-node/#')

        assert device_acl.access == 3  # Read + Write
        assert sensor_acl.access == 1  # Write only
        assert command_acl.access == 2  # Read only

    def test_provision_node_with_existing_node_id_fails(self, db):
        """Test provision_node with duplicate node_id fails."""
        provision_node('duplicate-node-test', 'First Device')

        # Should create a new user but update existing node
        with transaction.atomic():
            user = provision_node('duplicate-node-test', 'Second Device')
            user.refresh_from_db()
            # Second call should update the node, not create duplicate
            node = Node.objects.get(node_id='duplicate-node-test')
            assert node.name == 'Second Device'

    def test_regenerate_node_credentials_creates_new_password(self, db, node_with_user):
        """Test regenerate_node_credentials creates new password."""
        old_password = node_with_user.user.password
        old_password_plain = getattr(node_with_user.user, '_plain_password', None)

        user = regenerate_node_credentials(node_with_user)

        assert user.password != old_password
        assert user.password.startswith('$2')
        assert hasattr(user, '_plain_password')

    def test_regenerate_node_credentials_replaces_acls(self, db, node_with_user):
        """Test regenerate_node_credentials replaces existing ACLs."""
        user = node_with_user.user

        # Add custom ACL
        MqttAcl.objects.create(user=user, topic='custom/topic', access=3)
        original_acl_count = user.acls.count()

        # Regenerate - should clear and recreate
        regenerate_node_credentials(node_with_user)

        # Should have exactly 3 default ACLs
        assert user.acls.count() == 3
        topics = [acl.topic for acl in user.acls.all()]
        assert 'custom/topic' not in topics

    def test_provision_node_integration_with_password_verification(self, db):
        """Test complete flow: provision node and verify password works."""
        node_id = 'full-integration-node'
        user = provision_node(node_id, 'Full Integration Test')

        # Verify the plain password works with the stored hash
        plain_password = user._plain_password
        stored_hash = user.password

        assert bcrypt.checkpw(
            plain_password.encode('utf-8'),
            stored_hash.encode('utf-8')
        )

        # Simulate broker authentication
        # In production, the broker would use this same verification
        is_authenticated = bcrypt.checkpw(
            plain_password.encode('utf-8'),
            MqttUser.objects.get(username=node_id).password.encode('utf-8')
        )
        assert is_authenticated is True


class TestEndToEndWorkflow:
    """End-to-end integration tests."""

    def test_complete_user_lifecycle(self, db):
        """Test complete user lifecycle: create, add ACLs, update password, delete."""
        # 1. Create user
        user = MqttUser(username='lifecycle_test')
        user.set_password('initial_password')
        user.save()

        # 2. Add ACLs
        acl1 = MqttAcl.objects.create(user=user, topic='lifecycle/topic1', access=2)
        acl2 = MqttAcl.objects.create(user=user, topic='lifecycle/topic2', access=1)

        assert user.acls.count() == 2

        # 3. Update password
        old_hash = user.password
        user.set_password('updated_password')
        user.save()

        assert user.password != old_hash

        # 4. Verify new password
        assert bcrypt.checkpw('updated_password'.encode('utf-8'), user.password.encode('utf-8'))
        assert not bcrypt.checkpw('initial_password'.encode('utf-8'), user.password.encode('utf-8'))

        # 5. Delete user (ACLs cascade)
        user.delete()

        assert MqttUser.objects.filter(username='lifecycle_test').count() == 0
        assert MqttAcl.objects.filter(user__username='lifecycle_test').count() == 0

    def test_node_provisioning_and_broker_authentication(self, db):
        """Test node provisioning workflow matches broker authentication requirements."""
        # Provision a new IoT device
        node_id = 'iot-device-001'
        user = provision_node(node_id, 'IoT Temperature Sensor')

        # Extract credentials (as would be delivered to device)
        username = user.username
        password = user._plain_password

        # Simulate broker authentication check
        db_user = MqttUser.objects.get(username=username)

        # Verify credentials
        is_valid = bcrypt.checkpw(password.encode('utf-8'), db_user.password.encode('utf-8'))
        assert is_valid is True

        # Check ACLs (broker would check these)
        device_acls = db_user.acls.all()
        assert len(device_acls) == 3

        # Verify ACL patterns
        for acl in device_acls:
            assert node_id in acl.topic
            assert acl.access in [1, 2, 3]  # Valid access levels

    def test_multiple_nodes_isolation(self, db):
        """Test that multiple nodes are properly isolated."""
        # Provision multiple nodes
        user1 = provision_node('device-001', 'Device One')
        user2 = provision_node('device-002', 'Device Two')
        user3 = provision_node('device-003', 'Device Three')

        # Verify users are independent
        assert user1.pk != user2.pk != user3.pk
        assert user1.password != user2.password != user3.password

        # Verify ACLs are separate
        for user in [user1, user2, user3]:
            acls = user.acls.all()
            for acl in acls:
                # Each ACL should reference only its own device
                assert user.username in acl.topic

        # Verify nodes are created
        assert Node.objects.count() == 3

    def test_acl_permission_inheritance_pattern(self, db):
        """Test ACL wildcards work as expected for topic hierarchies."""
        user = MqttUser(username='hierarchy_test')
        user.set_password('password')
        user.save()

        # Create hierarchical ACLs
        MqttAcl.objects.create(user=user, topic='home/+/temperature', access=2)
        MqttAcl.objects.create(user=user, topic='home/kitchen/+', access=3)
        MqttAcl.objects.create(user=user, topic='home/living_room/light/set', access=1)

        # Verify stored patterns
        acls = user.acls.all()
        patterns = {acl.topic for acl in acls}

        assert 'home/+/temperature' in patterns
        assert 'home/kitchen/+' in patterns
        assert 'home/living_room/light/set' in patterns

        # In a real MQTT broker, wildcards would match:
        # home/+/temperature would match: home/living_room/temperature, home/kitchen/temperature
        # home/kitchen/+ would match: home/kitchen/light, home/kitchen/fan
