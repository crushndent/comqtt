from django.db import models


class MqttUser(models.Model):
    id = models.BigAutoField(primary_key=True)
    username = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=255)
    allow = models.SmallIntegerField(default=1)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mqtt_user'
        managed = True
        verbose_name = 'MQTT User'
        verbose_name_plural = 'MQTT Users'

    def __str__(self):
        return self.username

    def set_password(self, raw_password):
        import bcrypt
        salt = bcrypt.gensalt()
        self.password = bcrypt.hashpw(raw_password.encode('utf-8'), salt).decode('utf-8')

    @classmethod
    def make_random_password(cls, length=12):
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))


class MqttAcl(models.Model):
    ACCESS_CHOICES = [
        (0, 'Deny'),
        (1, 'Write'),
        (2, 'Read'),
        (3, 'Read + Write'),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(MqttUser, on_delete=models.CASCADE, db_column='username', to_field='username', related_name='acls')
    topic = models.CharField(max_length=255)
    access = models.SmallIntegerField(default=2, choices=ACCESS_CHOICES)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mqtt_acl'
        managed = True
        verbose_name = 'MQTT ACL'
        verbose_name_plural = 'MQTT ACLs'
        unique_together = [['user', 'topic']]

    def __str__(self):
        return f"{self.user.username} - {self.topic}"


class Node(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    id = models.BigAutoField(primary_key=True)
    node_id = models.CharField(max_length=255, unique=True, help_text="Unique identifier (e.g., MAC address or UUID)")
    name = models.CharField(max_length=255, blank=True, help_text="Human-readable name")
    user = models.OneToOneField(
        MqttUser,
        on_delete=models.CASCADE,
        related_name='node',
        null=True,
        blank=True
    )
    location = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mqtt_node'
        managed = True
        verbose_name = 'Node'
        verbose_name_plural = 'Nodes'
        ordering = ['-created']

    def __str__(self):
        return f"{self.name or self.node_id} ({self.node_id})"
