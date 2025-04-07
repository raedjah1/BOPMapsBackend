#!/usr/bin/env python
"""
Debug script for sample data generation
"""

import traceback
from django.utils import timezone
from django.contrib.gis.geos import Point
from users.models import User

try:
    print("Starting sample data debug...")
    
    admin_user, created = User.objects.get_or_create(
        username="bopmaps",
        defaults={
            "email": "admin@bopmaps.com",
            "is_staff": True,
            "is_superuser": True,
            "first_name": "BOP",
            "last_name": "Admin",
        }
    )
    
    if created:
        admin_user.set_password("bopmaps")
        admin_user.save()
        print("Created admin user: bopmaps")
    else:
        print("Admin user already exists")
    
    # Try creating a new test user
    test_user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="password123",
        first_name="Test",
        last_name="User",
        bio="This is a test user.",
    )
    
    # Set a location for the test user
    test_user.location = Point(-74.0060, 40.7128)  # New York
    test_user.save()
    
    print(f"Created test user: {test_user.username}")
    print(f"Total users: {User.objects.count()}")
    
    print("Debug successful!")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc() 