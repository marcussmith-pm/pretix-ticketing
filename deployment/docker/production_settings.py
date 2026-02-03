import os
from urllib.parse import urlparse
from pretix.settings import *

# Parse DATABASE_URL from Railway environment variable
if 'DATABASE_URL' in os.environ:
    db_url = urlparse(os.environ['DATABASE_URL'])

    # Override database settings from DATABASE_URL
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': db_url.path[1:],  # Remove leading slash
            'USER': db_url.username,
            'PASSWORD': db_url.password,
            'HOST': db_url.hostname,
            'PORT': db_url.port or 5432,
            'CONN_MAX_AGE': 120,
            'CONN_HEALTH_CHECKS': True,
        }
    }

LOGGING['handlers']['mail_admins']['include_html'] = True
STORAGES["staticfiles"]["BACKEND"] = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
