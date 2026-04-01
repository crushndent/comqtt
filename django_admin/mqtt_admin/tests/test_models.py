import pytest
import bcrypt
from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist
from mqtt_admin.models import MqttUser, MqttAcl, Node


class TestMqttUser:
    """Tests for the MqttUser model."""

    def test_user_creation(self, db):
        """Test basic MqttUser creation."""
        user = MqttUser(username='newuser')
        user.set_password('securepassword')
        user.save()

        assert user.pk is not None
        assert user.username == 'newuser'
        assert user.allow == 1  # Default value
        assert user.created is not None
        assert user.updated is not None

    def test_user_str_representation(self, mqtt_user):
        """Test __str__ method returns username."""
        assert str(mqtt_user) == 'testuser'

    def test_set_password_produces_bcrypt_hash(self, db):
        """Test that set_password produces a valid bcrypt hash."""
        user = MqttUser(username='hashtest')
        raw_password = 'testpassword123'
        user.set_password(raw_password)
        user.save()

        # Verify the stored password is a valid bcrypt hash
        assert user.password.startswith('$2')
        assert bcrypt.checkpw(raw_password.encode('utf-8'), user.password.encode('utf-8'))

    def test_password_never_stored_plaintext(self, db):
        """Test that password is never stored in plaintext."""
        plaintext_password = 'mysecretpassword'
        user = MqttUser(username='secrettest')
        user.set_password(plaintext_password)
        user.save()

        # Reload from database to ensure no plaintext leakage
        user.refresh_from_db()
        assert user.password != plaintext_password
        assert not plaintext_password in user.password
        assert user.password.startswith('$2')  # bcrypt identifier

    def test_unique_username_constraint(self, db):
        """Test that username must be unique."""
        user1 = MqttUser(username='uniqueuser')
        user1.set_password('password1')
        user1.save()

        user2 = MqttUser(username='uniqueuser')
        user2.set_password('password2')

        with pytest.raises(IntegrityError):
            user2.save()

    def test_make_random_password(self, db):
        """Test random password generation."""
        # Default length is 12
        password1 = MqttUser.make_random_password()
        assert len(password1) == 12

        # Custom length
        password2 = MqttUser.make_random_password(length=20)
        assert len(password2) == 20

        # Passwords should be different each time
        password3 = MqttUser.make_random_password()
        assert password1 != password3

    def test_default_allow_value(self, db):
        """Test that allow field defaults to 1."""
        user = MqttUser(username='allowtest')
        user.set_password('password')
        user.save()

        assert user.allow == 1

    def test_allow_value_can_be_changed(self, db):
        """Test that allow field can be set to 0."""
        user = MqttUser(username='blockeduser')
        user.set_password('password')
        user.allow = 0
        user.save()

        assert user.allow == 0

    def test_auto_timestamps(self, db):
        """Test created and updated timestamps are auto-set."""
        user = MqttUser(username='timetest')
        user.set_password('password')
        user.save()

        assert user.created is not None
        assert user.updated is not None
        created_time = user.created

        # Update should change updated but not created
        user.allow = 0
        user.save()

        assert user.created == created_time
        assert user.updated > user.created or user.updated == user.created

    def test_update_password(self, mqtt_user):
        """Test updating password for existing user."""
        old_password_hash = mqtt_user.password
        new_password = 'newpassword456'

        mqtt_user.set_password(new_password)
        mqtt_user.save()

        assert mqtt_user.password != old_password_hash
        assert bcrypt.checkpw(new_password.encode('utf-8'), mqtt_user.password.encode('utf-8'))


class TestMqttAcl:
    """Tests for the MqttAcl model."""

    def test_acl_creation(self, db, mqtt_user):
        """Test basic ACL creation."""
        acl = MqttAcl.objects.create(
            username=mqtt_user.username,
            topic='test/topic',
            access=2  # Read
        )

        assert acl.pk is not None
        assert acl.username == mqtt_user.username
        assert acl.topic == 'test/topic'
        assert acl.access == 2

    def test_acl_str_representation(self, mqtt_acl, mqtt_user):
        """Test __str__ method returns user-topic combination."""
        assert str(mqtt_acl) == f'{mqtt_user.username} - test/topic/#'

    def test_access_level_choices(self, db, mqtt_user):
        """Test all access level choices work correctly."""
        access_levels = [
            (0, 'Deny'),
            (1, 'Write'),
            (2, 'Read'),
            (3, 'Read + Write'),
        ]

        for level, label in access_levels:
            acl = MqttAcl.objects.create(
                username=mqtt_user.username,
                topic=f'test/topic/{level}',
                access=level
            )
            assert acl.access == level
            assert acl.get_access_display() == label

    def test_default_access_level(self, db, mqtt_user):
        """Test default access level is Read (2)."""
        acl = MqttAcl.objects.create(
            username=mqtt_user.username,
            topic='test/default'
        )

        assert acl.access == 2

    def test_unique_user_topic_constraint(self, db, mqtt_user):
        """Test that (username, topic) combination must be unique."""
        MqttAcl.objects.create(
            username=mqtt_user.username,
            topic='unique/topic',
            access=2
        )

        with pytest.raises(IntegrityError):
            MqttAcl.objects.create(
                username=mqtt_user.username,
                topic='unique/topic',
                access=1
            )

    def test_same_topic_different_users(self, db, mqtt_user, mqtt_user_with_password):
        """Test same topic can be used for different users."""
        user2 = mqtt_user_with_password('user2', 'password2')

        acl1 = MqttAcl.objects.create(
            username=mqtt_user.username,
            topic='shared/topic',
            access=2
        )

        acl2 = MqttAcl.objects.create(
            username=user2.username,
            topic='shared/topic',
            access=1
        )

        assert acl1.topic == acl2.topic
        assert acl1.username != acl2.username

    def test_acl_cascade_delete(self, db, mqtt_user):
        """Test ACLs are deleted when user is deleted (via FK constraint)."""
        acl = MqttAcl.objects.create(
            username=mqtt_user.username,
            topic='cascade/test',
            access=3
        )

        acl_id = acl.pk
        mqtt_user.delete()

        with pytest.raises(ObjectDoesNotExist):
            MqttAcl.objects.get(pk=acl_id)

    def test_multiple_acls_per_user(self, db, mqtt_user):
        """Test a user can have multiple ACLs."""
        topics = [
            ('topic/1', 2),
            ('topic/2', 1),
            ('topic/3', 3),
        ]

        for topic, access in topics:
            MqttAcl.objects.create(
                username=mqtt_user.username,
                topic=topic,
                access=access
            )

        assert MqttAcl.objects.filter(username=mqtt_user.username).count() == 3

    def test_filter_by_username(self, mqtt_acl, mqtt_user):
        """Test filtering ACLs by username."""
        acls = MqttAcl.objects.filter(username=mqtt_user.username)
        assert mqtt_acl in acls


class TestNode:
    """Tests for the Node model."""

    def test_node_creation(self, db):
        """Test basic Node creation."""
        node = Node.objects.create(
            node_id='node-001',
            name='Test Node',
            location='Building A',
            status='active'
        )

        assert node.pk is not None
        assert node.node_id == 'node-001'
        assert node.name == 'Test Node'
        assert node.location == 'Building A'
        assert node.status == 'active'

    def test_node_str_representation_with_name(self, db):
        """Test __str__ method with name set."""
        node = Node.objects.create(
            node_id='node-002',
            name='My Named Node'
        )

        assert str(node) == 'My Named Node (node-002)'

    def test_node_str_representation_without_name(self, db):
        """Test __str__ method without name."""
        node = Node.objects.create(
            node_id='node-003'
        )

        assert str(node) == 'node-003 (node-003)'

    def test_unique_node_id_constraint(self, db):
        """Test that node_id must be unique."""
        Node.objects.create(node_id='unique-node')

        with pytest.raises(IntegrityError):
            Node.objects.create(node_id='unique-node')

    def test_node_optional_user(self, db):
        """Test that user field is optional."""
        node = Node.objects.create(
            node_id='node-no-user',
            name='Node without user'
        )

        assert node.user is None

    def test_node_with_user(self, node_with_user, mqtt_user):
        """Test Node linked to an MQTT user."""
        assert node_with_user.user == mqtt_user
        assert node_with_user.node == mqtt_user.node

    def test_node_status_choices(self, db):
        """Test status choices."""
        active_node = Node.objects.create(
            node_id='active-node',
            status='active'
        )

        inactive_node = Node.objects.create(
            node_id='inactive-node',
            status='inactive'
        )

        assert active_node.status == 'active'
        assert inactive_node.status == 'inactive'

    def test_default_status(self, db):
        """Test default status is 'active'."""
        node = Node.objects.create(node_id='default-status-node')
        assert node.status == 'active'

    def test_auto_timestamps(self, db):
        """Test created and updated timestamps."""
        node = Node.objects.create(node_id='time-node')

        assert node.created is not None
        assert node.updated is not None

        created_time = node.created

        # Update should change updated but not created
        node.name = 'Updated Name'
        node.save()

        assert node.created == created_time

    def test_ordering_by_created_desc(self, db):
        """Test default ordering by created descending."""
        Node.objects.all().delete()

        node1 = Node.objects.create(node_id='node-1')
        node2 = Node.objects.create(node_id='node-2')
        node3 = Node.objects.create(node_id='node-3')

        nodes = list(Node.objects.all())
        assert nodes[0] == node3
        assert nodes[1] == node2
        assert nodes[2] == node1

    def test_cascade_delete_with_user(self, node_with_user, mqtt_user):
        """Test Node behavior when linked user is deleted."""
        node_id = node_with_user.pk
        mqtt_user.delete()

        # Node should be deleted due to CASCADE
        with pytest.raises(ObjectDoesNotExist):
            Node.objects.get(pk=node_id)

    def test_update_node_user(self, db, mqtt_user, mqtt_user_with_password):
        """Test updating the user associated with a node."""
        node = Node.objects.create(
            node_id='switch-user-node',
            user=mqtt_user
        )

        user2 = mqtt_user_with_password('newuser', 'password')
        node.user = user2
        node.save()

        node.refresh_from_db()
        assert node.user == user2
