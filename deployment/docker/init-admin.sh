#!/bin/bash
# Script to create initial admin user if it doesn't exist

cd /pretix/src

# Set environment variables for Django
export DJANGO_SETTINGS_MODULE=production_settings
export DATA_DIR=/data

# Check if superuser already exists
python3 manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); exit(0) if User.objects.filter(is_superuser=True).exists() else exit(1)"

if [ $? -eq 1 ]; then
    echo "Creating superuser..."

    # Check if ADMIN_PASSWORD is set, otherwise use environment variables or defaults
    ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
    ADMIN_EMAIL=${ADMIN_EMAIL:-admin@example.com}
    ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin123}

    # Try using create_admin.py script if it exists, otherwise fall back to Django command
    if [ -f "/pretix/src/create_admin.py" ]; then
        python3 /pretix/src/create_admin.py
    else
        # Fallback: Use Django shell to create user
        python3 manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$ADMIN_USERNAME').exists():
    User.objects.create_superuser('$ADMIN_USERNAME', '$ADMIN_EMAIL', '$ADMIN_PASSWORD')
    print('Created superuser: $ADMIN_USERNAME')
else:
    print('User already exists')
"
    fi
else
    echo "Superuser already exists"
fi
