import secrets
import string
from typing import Optional

from .models import MqttUser, MqttAcl, Node


def provision_node(node_id: str, node_name: str = None) -> MqttUser:
    """
    Provision a new node by creating an MQTT user with appropriate ACLs.
    
    Args:
        node_id: Unique identifier for the node (e.g., MAC address or UUID)
        node_name: Optional human-readable name for the node
        
    Returns:
        The created or existing MqttUser instance
    """
    # Check if user already exists
    try:
        user = MqttUser.objects.get(username=node_id)
        # User exists - regenerate credentials
        password = _generate_secure_password()
        user.set_password(password)
        user.save()
        # Clear existing ACLs and recreate
        MqttAcl.objects.filter(user=user).delete()
        _create_node_acls(user, node_id)
    except MqttUser.DoesNotExist:
        # Generate a random secure password
        password = _generate_secure_password()
        
        # Create the MQTT user
        user = MqttUser(username=node_id)
        user.set_password(password)
        user.save()
        
        # Create default ACL entries
        _create_node_acls(user, node_id)
    
    # Create or update the Node record
    node, created = Node.objects.update_or_create(
        node_id=node_id,
        defaults={
            'name': node_name or node_id,
            'user': user,
            'status': 'active'
        }
    )
    
    # Store the plain password temporarily on the user object for retrieval
    user._plain_password = password
    
    return user


def regenerate_node_credentials(node: Node) -> MqttUser:
    """
    Regenerate credentials for an existing node.
    
    Args:
        node: The Node instance to regenerate credentials for
        
    Returns:
        The updated MqttUser instance
    """
    if not node.user:
        # If no user exists, create new credentials
        return provision_node(node.node_id, node.name)
    
    user = node.user
    
    # Generate new password
    new_password = _generate_secure_password()
    user.set_password(new_password)
    user.save()
    
    # Clear existing ACLs and recreate them
    MqttAcl.objects.filter(user=user).delete()
    _create_node_acls(user, node.node_id)
    
    # Store the plain password temporarily on the user object for retrieval
    user._plain_password = new_password
    
    return user


def _generate_secure_password(length: int = 32) -> str:
    """Generate a cryptographically secure random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _create_node_acls(user: MqttUser, node_id: str) -> None:
    """
    Create default ACL entries for a node.

    ACLs created:
    - nodes/{node_id}/# - Read+Write (for device communication)
    - sensors/{node_id}/# - Write only (for sensor data)
    - commands/{node_id}/# - Read only (for receiving commands)
    """
    # Device communication: Read + Write
    MqttAcl.objects.create(
        user=user,
        topic=f'nodes/{node_id}/#',
        access=3  # Read + Write
    )

    # Sensor data: Write only
    MqttAcl.objects.create(
        user=user,
        topic=f'sensors/{node_id}/#',
        access=1  # Write
    )

    # Commands: Read only
    MqttAcl.objects.create(
        user=user,
        topic=f'commands/{node_id}/#',
        access=2  # Read
    )
