#!/bin/bash
# Script to create initial admin user if it doesn't exist

cd /pretix/src

# Check if superuser already exists
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); exit(0) if User.objects.filter(is_superuser=True).exists() else exit(1)"

if [ $? -eq 1 ]; then
    echo "Creating superuser..."
    python manage.py createsuperuser \
        --username admin \
        --email admin@example.com \
        --noinput || \
    python manage.py createsuperuser
else
    echo "Superuser already exists"
fi
