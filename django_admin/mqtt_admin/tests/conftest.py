import pytest
import bcrypt
from django.contrib.auth.models import User as DjangoUser
from mqtt_admin.models import MqttUser, MqttAcl, Node


@pytest.fixture
def mqtt_user(db):
    """Create a basic MQTT user for testing."""
    user = MqttUser(username='testuser')
    user.set_password('testpassword123')
    user.save()
    return user


@pytest.fixture
def mqtt_user_with_password(db):
    """Create an MQTT user with a specific password."""
    def _create_user(username, password):
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()
        return user
    return _create_user


@pytest.fixture
def mqtt_acl(db, mqtt_user):
    """Create a basic ACL entry for testing."""
    acl = MqttAcl.objects.create(
        username=mqtt_user.username,
        topic='test/topic/#',
        access=3  # Read + Write
    )
    return acl


@pytest.fixture
def multiple_acls(db, mqtt_user):
    """Create multiple ACL entries for a user."""
    acls = []
    topics = [
        ('sensors/+/temperature', 2),  # Read
        ('sensors/+/humidity', 2),     # Read
        ('commands/+/set', 1),         # Write
        ('admin/config', 3),           # Read + Write
    ]
    for topic, access in topics:
        acl = MqttAcl.objects.create(
            username=mqtt_user.username,
            topic=topic,
            access=access
        )
        acls.append(acl)
    return acls


@pytest.fixture
def node(db):
    """Create a basic Node for testing."""
    node = Node.objects.create(
        node_id='test-node-001',
        name='Test Node',
        location='Test Location',
        status='active'
    )
    return node


@pytest.fixture
def node_with_user(db, mqtt_user):
    """Create a Node linked to an MQTT user."""
    node = Node.objects.create(
        node_id='provisioned-node-001',
        name='Provisioned Node',
        user=mqtt_user,
        status='active'
    )
    return node


@pytest.fixture
def multiple_users(db):
    """Create multiple MQTT users for testing."""
    users = []
    for i in range(5):
        user = MqttUser(username=f'user_{i}')
        user.set_password(f'password_{i}')
        user.save()
        users.append(user)
    return users


@pytest.fixture
def admin_user(db):
    """Create a Django admin user for testing admin interface."""
    user = DjangoUser.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='adminpassword123'
    )
    return user


@pytest.fixture
def client_with_admin(client, admin_user):
    """Create a logged-in admin client."""
    client.force_login(admin_user)
    return client


@pytest.fixture
def bcrypt_password():
    """Generate a bcrypt hash for testing password verification."""
    def _hash_password(password):
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    return _hash_password


@pytest.fixture
def verify_bcrypt():
    """Verify a password against a bcrypt hash."""
    def _verify(password, hashed):
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    return _verify


@pytest.fixture
def sample_topics():
    """Return sample MQTT topics for testing."""
    return [
        'home/living_room/temperature',
        'home/living_room/humidity',
        'home/kitchen/light',
        'sensors/+/data',
        'commands/device_001/reset',
        '$SYS/broker/clients/connected',
    ]
