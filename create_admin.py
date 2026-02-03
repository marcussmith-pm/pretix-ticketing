#!/usr/bin/env python3
"""
Quick script to create admin user via environment variables
Run this in Railway console with: python create_admin.py
"""

import os
import sys

# Setup Django - use pretix module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'production_settings')
sys.path.insert(0, '/pretix/src')

# Import pretix to get Django
from pretix import django
django.setup()

from django.contrib.auth import get_user_model

# Get environment variables or use defaults
username = os.environ.get('ADMIN_USERNAME', 'admin')
email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
password = os.environ.get('ADMIN_PASSWORD', 'admin123')

User = get_user_model()

# Check if user already exists
if User.objects.filter(username=username).exists():
    print(f"User '{username}' already exists")
else:
    # Create superuser
    user = User.objects.create_superuser(
        username=username,
        email=email,
        password=password
    )
    print(f"Created superuser: {username}")
    print(f"Email: {email}")
    print(f"Password: {password}")
