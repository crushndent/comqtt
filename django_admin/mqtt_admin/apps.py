from django.apps import AppConfig


class MqttAdminConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mqtt_admin'
    verbose_name = 'MQTT Admin'
