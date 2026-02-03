#!/usr/bin/env python3
"""
Quick script to create admin user via environment variables
Run this in Railway console with: python create_admin.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'production_settings')
os.environ.setdefault('DATA_DIR', '/data')

# Add src to path
sys.path.insert(0, '/pretix/src')

# Initialize Django
django.setup()

from django.contrib.auth import get_user_model

# Get environment variables or use defaults
email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
password = os.environ.get('ADMIN_PASSWORD', 'admin123')

User = get_user_model()

# Check if user already exists (by email)
if User.objects.filter(email=email).exists():
    print(f"User with email '{email}' already exists")
else:
    # Create superuser using pretix's custom user manager
    # pretix uses email as the username
    user = User.objects.create_superuser(
        email=email,
        password=password
    )
    print(f"Created superuser: {email}")
    print(f"Password: {password}")
