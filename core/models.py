from django.db import models
import bcrypt

class MqttUser(models.Model):
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255, help_text="Bcrypt hashed password")
    is_superuser = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        # Hash password with bcrypt
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(raw_password.encode('utf-8'), salt)
        self.password = hashed.decode('utf-8')

    def check_password(self, raw_password):
        return bcrypt.checkpw(raw_password.encode('utf-8'), self.password.encode('utf-8'))

    def __str__(self):
        return self.username

class MqttAcl(models.Model):
    ACCESS_CHOICES = [
        (1, 'Read Only'),
        (2, 'Write Only'),
        (3, 'Read and Write'),
    ]

    user = models.ForeignKey(MqttUser, on_delete=models.CASCADE, related_name='acls')
    topic = models.CharField(max_length=255)
    access = models.IntegerField(choices=ACCESS_CHOICES, default=1)

    class Meta:
        unique_together = ('user', 'topic')

    def __str__(self):
        return f"{self.user.username} - {self.topic} ({self.get_access_display()})"
