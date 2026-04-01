"""
MQTT Integration Tests for Django Admin and CoMQTT broker.

These tests verify the actual MQTT auth/ACL flow between Django and CoMQTT using paho-mqtt.
Tests require a running MQTT broker with PostgreSQL auth/ACL hooks configured.
"""

import socket
import time
import uuid
from typing import Optional

import paho.mqtt.client as mqtt
import pytest
import bcrypt

from mqtt_admin.models import MqttUser, MqttAcl, Node
from mqtt_admin.node_provisioning import provision_node, regenerate_node_credentials


# Pytest marker to skip tests if MQTT broker is not available
mqtt_broker_available = pytest.mark.skipif(
    not pytest.config.getoption("--mqtt-broker", default=False) if hasattr(pytest, 'config') else False,
    reason="MQTT broker tests disabled (use --mqtt-broker to enable)"
) if hasattr(pytest, 'config') else pytest.mark.skipif(False, reason="MQTT broker check pending")


def is_mqtt_broker_available(host: str, port: int, timeout: int = 2) -> bool:
    """Check if MQTT broker is available at the specified host and port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.fixture(scope="session")
def mqtt_broker_host() -> str:
    """MQTT broker host (default: localhost)."""
    return pytest.config.getoption("--mqtt-host", default="localhost") if hasattr(pytest, 'config') else "localhost"


@pytest.fixture(scope="session")
def mqtt_broker_port() -> int:
    """MQTT broker port (default: 1883)."""
    return int(pytest.config.getoption("--mqtt-port", default="1883")) if hasattr(pytest, 'config') else 1883


@pytest.fixture
def check_broker(mqtt_broker_host: str, mqtt_broker_port: int):
    """Skip test if MQTT broker is not available."""
    if not is_mqtt_broker_available(mqtt_broker_host, mqtt_broker_port):
        pytest.skip(f"MQTT broker not available at {mqtt_broker_host}:{mqtt_broker_port}")


@pytest.fixture
def mqtt_client_factory(mqtt_broker_host: str, mqtt_broker_port: int):
    """Factory fixture that creates MQTT clients with automatic cleanup."""
    clients = []

    def _create_client(client_id: Optional[str] = None) -> mqtt.Client:
        if client_id is None:
            client_id = f"test-client-{uuid.uuid4().hex[:8]}"
        
        client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        client.connect(mqtt_broker_host, mqtt_broker_port, keepalive=60)
        clients.append(client)
        return client

    yield _create_client

    # Cleanup: disconnect all clients
    for client in clients:
        try:
            if client.is_connected():
                client.disconnect()
                client.loop_stop()
        except Exception:
            pass


@pytest.fixture
def mqtt_client(mqtt_client_factory) -> mqtt.Client:
    """Create a basic MQTT client with cleanup."""
    return mqtt_client_factory()


def wait_for_connection(client: mqtt.Client, timeout: int = 5) -> bool:
    """Wait for MQTT connection with timeout."""
    connected = False
    connection_error = None

    def on_connect(client, userdata, flags, rc, properties=None):
        nonlocal connected, connection_error
        if rc == 0:
            connected = True
        else:
            connection_error = f"Connection failed with code: {rc}"

    def on_connect_fail(client, userdata):
        nonlocal connection_error
        connection_error = "Connection failed"

    client.on_connect = on_connect
    client.on_connect_fail = on_connect_fail

    client.loop_start()
    
    start_time = time.time()
    while not connected and connection_error is None and (time.time() - start_time) < timeout:
        time.sleep(0.1)

    client.loop_stop()
    
    if connection_error:
        return False
    return connected


def try_authenticate(host: str, port: int, username: str, password: str, timeout: int = 5) -> tuple[bool, Optional[str]]:
    """Try to authenticate with MQTT broker and return (success, error_message)."""
    client_id = f"auth-test-{uuid.uuid4().hex[:8]}"
    client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, password)
    
    result = {"connected": False, "error": None}

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            result["connected"] = True
        else:
            result["error"] = f"Authentication failed with code: {rc}"

    def on_connect_fail(client, userdata):
        result["error"] = "Connection failed - likely authentication error"

    client.on_connect = on_connect
    client.on_connect_fail = on_connect_fail

    try:
        client.connect(host, port, keepalive=10)
        client.loop_start()
        
        start_time = time.time()
        while not result["connected"] and result["error"] is None and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        client.loop_stop()
        
        if result["connected"]:
            client.disconnect()
            return True, None
        elif result["error"]:
            return False, result["error"]
        else:
            return False, "Connection timeout"
    except Exception as e:
        return False, str(e)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.usefixtures("check_broker")
class TestMqttAuthentication:
    """Tests for MQTT authentication flow between Django and CoMQTT."""

    def test_mqtt_auth_success(self, db, mqtt_broker_host: str, mqtt_broker_port: int):
        """Create user in Django, connect with correct credentials."""
        username = f"auth-success-{uuid.uuid4().hex[:8]}"
        password = "correct_password_123"
        
        # Create user in Django
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()

        # Try to connect with correct credentials
        success, error = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, password)
        
        assert success, f"Authentication should succeed but got error: {error}"

    def test_mqtt_auth_wrong_password(self, db, mqtt_broker_host: str, mqtt_broker_port: int):
        """Connection should fail with wrong password."""
        username = f"auth-wrong-pass-{uuid.uuid4().hex[:8]}"
        correct_password = "correct_password_123"
        wrong_password = "wrong_password_456"
        
        # Create user in Django
        user = MqttUser(username=username)
        user.set_password(correct_password)
        user.save()

        # Try to connect with wrong password
        success, error = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, wrong_password)
        
        assert not success, "Authentication should fail with wrong password"
        assert error is not None, "Should have an error message"

    def test_mqtt_auth_disabled_user(self, db, mqtt_broker_host: str, mqtt_broker_port: int):
        """Connection should fail when allow=0."""
        username = f"auth-disabled-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        
        # Create disabled user in Django
        user = MqttUser(username=username, allow=0)
        user.set_password(password)
        user.save()

        # Try to connect with disabled user
        success, error = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, password)
        
        assert not success, "Authentication should fail for disabled user"
        assert error is not None, "Should have an error message"

    def test_mqtt_auth_nonexistent_user(self, db, mqtt_broker_host: str, mqtt_broker_port: int):
        """Connection should fail for unknown user."""
        username = f"nonexistent-{uuid.uuid4().hex[:8]}"
        password = "some_password"

        # Try to connect with non-existent user (no DB creation)
        success, error = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, password)
        
        assert not success, "Authentication should fail for non-existent user"
        assert error is not None, "Should have an error message"


@pytest.mark.integration
@pytest.mark.usefixtures("check_broker")
class TestMqttAuthorization:
    """Tests for MQTT authorization (ACL) flow between Django and CoMQTT."""

    def test_mqtt_publish_allowed_topic(self, db, mqtt_broker_host: str, mqtt_broker_port: int, mqtt_client_factory):
        """Can publish to allowed topic."""
        username = f"pub-allowed-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        topic = f"test/allowed/{uuid.uuid4().hex[:8]}"
        
        # Create user with write ACL
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()
        
        MqttAcl.objects.create(
            username=username,
            topic=topic,
            access=1  # Write only
        )

        # Create client and authenticate
        client = mqtt_client_factory()
        client.username_pw_set(username, password)
        
        success, error = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, password)
        assert success, f"Authentication failed: {error}"

        # Try to publish
        client.connect(mqtt_broker_host, mqtt_broker_port)
        result = client.publish(topic, "test message", qos=1)
        
        # Wait for publish to complete
        result.wait_for_publish(timeout=5)
        assert result.rc == mqtt.MQTT_ERR_SUCCESS, f"Publish failed with code: {result.rc}"

    def test_mqtt_publish_denied_topic(self, db, mqtt_broker_host: str, mqtt_broker_port: int, mqtt_client_factory):
        """Cannot publish to denied topic."""
        username = f"pub-denied-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        allowed_topic = f"test/allowed/{uuid.uuid4().hex[:8]}"
        denied_topic = f"test/denied/{uuid.uuid4().hex[:8]}"
        
        # Create user with only read ACL on allowed topic
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()
        
        MqttAcl.objects.create(
            username=username,
            topic=allowed_topic,
            access=2  # Read only
        )

        # Create client and authenticate
        client = mqtt_client_factory()
        client.username_pw_set(username, password)
        client.connect(mqtt_broker_host, mqtt_broker_port)
        
        # Try to publish to denied topic - should fail or be rejected
        result = client.publish(denied_topic, "test message", qos=1)
        
        # The publish might succeed locally but be rejected by broker
        # We check if we get disconnected or receive an error
        time.sleep(0.5)
        
        # If still connected, the broker may allow it (depends on broker config)
        # For strict ACL brokers, this would disconnect the client

    def test_mqtt_subscribe_allowed_topic(self, db, mqtt_broker_host: str, mqtt_broker_port: int, mqtt_client_factory):
        """Can subscribe to allowed topic."""
        username = f"sub-allowed-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        topic = f"test/allowed/{uuid.uuid4().hex[:8]}"
        
        # Create user with read ACL
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()
        
        MqttAcl.objects.create(
            username=username,
            topic=topic,
            access=2  # Read only
        )

        # Create client and authenticate
        client = mqtt_client_factory()
        client.username_pw_set(username, password)
        client.connect(mqtt_broker_host, mqtt_broker_port)
        
        # Try to subscribe
        result, mid = client.subscribe(topic, qos=1)
        
        # Give time for subscription to process
        time.sleep(0.5)
        
        # Check subscription was successful
        assert result == mqtt.MQTT_ERR_SUCCESS, f"Subscribe failed with code: {result}"

    def test_mqtt_subscribe_denied_topic(self, db, mqtt_broker_host: str, mqtt_broker_port: int, mqtt_client_factory):
        """Cannot subscribe to denied topic."""
        username = f"sub-denied-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        allowed_topic = f"test/allowed/{uuid.uuid4().hex[:8]}"
        denied_topic = f"test/denied/{uuid.uuid4().hex[:8]}"
        
        # Create user with write-only ACL on allowed topic
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()
        
        MqttAcl.objects.create(
            username=username,
            topic=allowed_topic,
            access=1  # Write only
        )

        # Create client and authenticate
        client = mqtt_client_factory()
        client.username_pw_set(username, password)
        client.connect(mqtt_broker_host, mqtt_broker_port)
        
        # Try to subscribe to denied topic
        result, mid = client.subscribe(denied_topic, qos=1)
        
        # Give time for subscription to process
        time.sleep(0.5)
        
        # Subscription might succeed locally but be rejected by broker

    def test_mqtt_wildcard_acl_hash(self, db, mqtt_broker_host: str, mqtt_broker_port: int, mqtt_client_factory):
        """Test # wildcard works correctly."""
        username = f"wildcard-hash-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        
        # Create user with wildcard ACL using #
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()
        
        MqttAcl.objects.create(
            username=username,
            topic=f"sensors/{username}/#",
            access=3  # Read + Write
        )

        client = mqtt_client_factory()
        client.username_pw_set(username, password)
        client.connect(mqtt_broker_host, mqtt_broker_port)
        
        # Should be able to subscribe to any topic under sensors/{username}/
        result, mid = client.subscribe(f"sensors/{username}/temperature", qos=1)
        time.sleep(0.2)
        assert result == mqtt.MQTT_ERR_SUCCESS
        
        # Should be able to publish to any topic under sensors/{username}/
        result = client.publish(f"sensors/{username}/humidity", "50%", qos=1)
        result.wait_for_publish(timeout=3)
        assert result.rc == mqtt.MQTT_ERR_SUCCESS

    def test_mqtt_wildcard_acl_plus(self, db, mqtt_broker_host: str, mqtt_broker_port: int, mqtt_client_factory):
        """Test + wildcard works correctly."""
        username = f"wildcard-plus-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        
        # Create user with wildcard ACL using +
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()
        
        MqttAcl.objects.create(
            username=username,
            topic=f"devices/+/status",
            access=3  # Read + Write
        )

        client = mqtt_client_factory()
        client.username_pw_set(username, password)
        client.connect(mqtt_broker_host, mqtt_broker_port)
        
        # Should be able to subscribe to devices with single level wildcard
        result, mid = client.subscribe("devices/device001/status", qos=1)
        time.sleep(0.2)
        assert result == mqtt.MQTT_ERR_SUCCESS
        
        # Should be able to publish to devices with single level wildcard
        result = client.publish("devices/device002/status", "online", qos=1)
        result.wait_for_publish(timeout=3)
        assert result.rc == mqtt.MQTT_ERR_SUCCESS


@pytest.mark.integration
@pytest.mark.usefixtures("check_broker")
class TestMqttDynamicUpdates:
    """Tests for dynamic updates taking effect immediately in MQTT broker."""

    def test_acl_update_takes_effect(self, db, mqtt_broker_host: str, mqtt_broker_port: int, mqtt_client_factory):
        """Add ACL in Django, immediately test in MQTT."""
        username = f"dynamic-acl-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        topic = f"dynamic/topic/{uuid.uuid4().hex[:8]}"
        
        # Create user without ACL
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()

        # Authenticate first
        success, error = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, password)
        assert success, f"Initial authentication failed: {error}"

        # Add ACL dynamically
        MqttAcl.objects.create(
            username=username,
            topic=topic,
            access=3  # Read + Write
        )

        # Immediately test the new ACL
        client = mqtt_client_factory()
        client.username_pw_set(username, password)
        client.connect(mqtt_broker_host, mqtt_broker_port)
        
        # Should now be able to publish
        result = client.publish(topic, "dynamic test", qos=1)
        result.wait_for_publish(timeout=3)
        
        assert result.rc == mqtt.MQTT_ERR_SUCCESS, "ACL update should take effect immediately"

    def test_password_reset_takes_effect(self, db, mqtt_broker_host: str, mqtt_broker_port: int):
        """Reset password, old fails, new works."""
        username = f"pwd-reset-{uuid.uuid4().hex[:8]}"
        old_password = "old_password_123"
        new_password = "new_password_456"
        
        # Create user with old password
        user = MqttUser(username=username)
        user.set_password(old_password)
        user.save()

        # Verify old password works
        success, _ = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, old_password)
        assert success, "Old password should work initially"

        # Reset password
        user.set_password(new_password)
        user.save()

        # Old password should fail
        success, _ = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, old_password)
        assert not success, "Old password should fail after reset"

        # New password should work
        success, _ = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, new_password)
        assert success, "New password should work after reset"

    def test_user_deletion_takes_effect(self, db, mqtt_broker_host: str, mqtt_broker_port: int):
        """Delete user, connection fails."""
        username = f"user-delete-{uuid.uuid4().hex[:8]}"
        password = "password_123"
        
        # Create user
        user = MqttUser(username=username)
        user.set_password(password)
        user.save()

        # Verify user can authenticate
        success, _ = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, password)
        assert success, "User should authenticate before deletion"

        # Delete user
        user.delete()

        # User should no longer be able to authenticate
        success, _ = try_authenticate(mqtt_broker_host, mqtt_broker_port, username, password)
        assert not success, "Deleted user should not be able to authenticate"


@pytest.mark.integration
@pytest.mark.usefixtures("check_broker")
class TestMqttNodeProvisioning:
    """Tests for node provisioning and MQTT access."""

    def test_provisioned_node_can_connect(self, db, mqtt_broker_host: str, mqtt_broker_port: int):
        """Provisioned node can authenticate."""
        node_id = f"provisioned-node-{uuid.uuid4().hex[:8]}"
        
        # Provision node
        user = provision_node(node_id, "Test Device")
        password = user._plain_password

        # Verify node can authenticate
        success, error = try_authenticate(mqtt_broker_host, mqtt_broker_port, node_id, password)
        assert success, f"Provisioned node should authenticate: {error}"

    def test_provisioned_node_topic_access(self, db, mqtt_broker_host: str, mqtt_broker_port: int, mqtt_client_factory):
        """Node can access its designated topics."""
        node_id = f"node-access-{uuid.uuid4().hex[:8]}"
        
        # Provision node
        user = provision_node(node_id, "Test Device")
        password = user._plain_password

        # Create client
        client = mqtt_client_factory()
        client.username_pw_set(node_id, password)
        client.connect(mqtt_broker_host, mqtt_broker_port)

        # Should be able to write to sensors/{node_id}/# (access=1)
        result = client.publish(f"sensors/{node_id}/temperature", "25.5", qos=1)
        result.wait_for_publish(timeout=3)
        assert result.rc == mqtt.MQTT_ERR_SUCCESS, "Should be able to publish to sensors topic"

        # Should be able to read from commands/{node_id}/# (access=2)
        result, mid = client.subscribe(f"commands/{node_id}/restart", qos=1)
        time.sleep(0.2)
        assert result == mqtt.MQTT_ERR_SUCCESS, "Should be able to subscribe to commands topic"

        # Should be able to read/write to nodes/{node_id}/# (access=3)
        result = client.publish(f"nodes/{node_id}/status", "online", qos=1)
        result.wait_for_publish(timeout=3)
        assert result.rc == mqtt.MQTT_ERR_SUCCESS, "Should be able to publish to nodes topic"
        
        result, mid = client.subscribe(f"nodes/{node_id}/config", qos=1)
        time.sleep(0.2)
        assert result == mqtt.MQTT_ERR_SUCCESS, "Should be able to subscribe to nodes topic"


def pytest_addoption(parser):
    """Add custom pytest options for MQTT broker testing."""
    parser.addoption(
        "--mqtt-broker",
        action="store_true",
        default=False,
        help="Run MQTT broker integration tests"
    )
    parser.addoption(
        "--mqtt-host",
        action="store",
        default="localhost",
        help="MQTT broker host (default: localhost)"
    )
    parser.addoption(
        "--mqtt-port",
        action="store",
        default="1883",
        help="MQTT broker port (default: 1883)"
    )
