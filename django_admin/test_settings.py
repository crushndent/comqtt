"""
Test settings for running tests without PostgreSQL.
Uses SQLite with modified model Meta to allow table creation.
"""

from mqtt_admin_project.settings import *

# Use SQLite for testing
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Disable logging during tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
}

# Use fast password hasher for testing
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Secret key for testing
SECRET_KEY = 'test-secret-key-not-for-production'

# Debug mode for tests
DEBUG = True

# Allowed hosts
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver']

# Disable HTTPS redirects in tests
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

# Session and message middleware required for admin actions
# django.contrib.messages is already in base INSTALLED_APPS

# Ensure messages middleware is included (SessionMiddleware must be before MessageMiddleware)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # Required before auth and messages
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',  # Required for admin actions
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Required for messages framework
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'
