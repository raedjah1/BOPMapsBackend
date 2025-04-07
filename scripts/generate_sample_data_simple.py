#!/usr/bin/env python
"""
Simplified script to generate sample data for BOPMaps development.
This creates users, pins, and interactions, focusing on the core functionality.

Usage:
    python manage.py shell -c "exec(open('scripts/generate_sample_data_simple.py').read())"
"""

import random
import traceback
from datetime import timedelta
from django.utils import timezone
from django.contrib.gis.geos import Point
from django.db import transaction, models

from users.models import User
from pins.models import Pin, PinInteraction
from friends.models import Friend
from gamification.models import PinSkin
from geo.models import TrendingArea

# Configuration
NUM_USERS = 10
NUM_PINS = 30
NUM_FRIEND_CONNECTIONS = 15
NUM_PIN_INTERACTIONS = 50

# Sample locations (coordinates for major cities)
LOCATIONS = [
    # City centers in format: (longitude, latitude)
    # New York
    (-73.9857, 40.7484),
    # Los Angeles
    (-118.2437, 34.0522),
    # Chicago
    (-87.6298, 41.8781),
    # San Francisco
    (-122.4194, 37.7749),
    # London
    (-0.1278, 51.5074),
]

try:
    print("Starting sample data generation for BOPMaps...")
    
    # Create admin user if not exists
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
    
    # Create regular users
    print(f"Creating {NUM_USERS} sample users...")
    users = [admin_user]  # Add admin to users list
    
    for i in range(1, NUM_USERS + 1):
        username = f"user{i}"
        email = f"user{i}@example.com"
        
        # Skip if the user already exists
        if User.objects.filter(username=username).exists():
            print(f"User {username} already exists, skipping...")
            continue
            
        user = User.objects.create_user(
            username=username,
            email=email,
            password="password123",
            first_name=f"First{i}",
            last_name=f"Last{i}",
            bio=f"This is the bio for user {i}. They love music and sharing pins!",
        )
        
        # Set a random location
        lng, lat = random.choice(LOCATIONS)
        user.location = Point(lng, lat)
        user.save()
        
        users.append(user)
        print(f"Created user: {username}")
    
    # Create pin skins
    print("Creating pin skins...")
    skin_data = [
        {"name": "Default", "description": "The default pin skin", "is_premium": False},
        {"name": "Gold", "description": "A shiny gold pin", "is_premium": True},
        {"name": "Neon", "description": "A bright neon-colored pin", "is_premium": True},
    ]
    
    pin_skins = []
    for data in skin_data:
        skin, created = PinSkin.objects.get_or_create(
            name=data["name"],
            defaults={
                "description": data["description"],
                "is_premium": data["is_premium"],
            }
        )
        pin_skins.append(skin)
        if created:
            print(f"Created pin skin: {skin.name}")
        else:
            print(f"Pin skin {skin.name} already exists")
    
    # Create pins
    print(f"Creating {NUM_PINS} pins...")
    pins = []
    
    # Sample track data
    sample_tracks = [
        {
            "service": "spotify",
            "title": "Bohemian Rhapsody",
            "artist": "Queen",
            "album": "A Night at the Opera",
            "track_url": "https://open.spotify.com/track/sample1",
        },
        {
            "service": "apple",
            "title": "Billie Jean",
            "artist": "Michael Jackson",
            "album": "Thriller",
            "track_url": "https://music.apple.com/track/sample2",
        },
        {
            "service": "soundcloud",
            "title": "Lo-fi Beats",
            "artist": "Chill Producer",
            "album": "",
            "track_url": "https://soundcloud.com/track/sample3",
        },
    ]
    
    for i in range(NUM_PINS):
        # Get a random user and location
        user = random.choice(users)
        lng, lat = random.choice(LOCATIONS)
        
        # Add some randomness to location
        lng += random.uniform(-0.05, 0.05)
        lat += random.uniform(-0.05, 0.05)
        
        # Get a random track
        track = random.choice(sample_tracks)
        
        # Create the pin
        pin = Pin.objects.create(
            owner=user,
            location=Point(lng, lat),
            title=f"{user.username}'s {track['title']} pin",
            description=f"Check out this {track['title']} by {track['artist']}!",
            track_title=track['title'],
            track_artist=track['artist'],
            album=track['album'],
            track_url=track['track_url'],
            service=track['service'],
            skin=random.choice(pin_skins),
            rarity=random.choice(['common', 'uncommon', 'rare', 'epic', 'legendary']),
            is_private=random.random() < 0.2,  # 20% chance of being private
        )
        
        pins.append(pin)
        print(f"Created pin: {pin.title}")
    
    # Create friend connections
    print(f"Creating {NUM_FRIEND_CONNECTIONS} friend connections...")
    for i in range(NUM_FRIEND_CONNECTIONS):
        # Get two random users
        user1, user2 = random.sample(users, 2)
        
        # Check if connection already exists
        existing = Friend.objects.filter(
            (models.Q(requester=user1) & models.Q(recipient=user2)) |
            (models.Q(requester=user2) & models.Q(recipient=user1))
        ).first()
        
        if existing:
            print(f"Friend connection between {user1.username} and {user2.username} already exists")
            continue
        
        # Create the connection
        status = random.choice(['pending', 'accepted', 'rejected'])
        friend = Friend.objects.create(
            requester=user1,
            recipient=user2,
            status=status,
        )
        
        print(f"Created friend connection: {user1.username} -> {user2.username} ({status})")
    
    # Create pin interactions
    print(f"Creating {NUM_PIN_INTERACTIONS} pin interactions...")
    for i in range(NUM_PIN_INTERACTIONS):
        # Get a random user and pin
        user = random.choice(users)
        pin = random.choice(pins)
        
        # Skip if user is the pin owner
        if pin.owner == user:
            continue
        
        # Get a random interaction type
        interaction_type = random.choice(['view', 'collect', 'like', 'share'])
        
        # Check if this interaction already exists
        if PinInteraction.objects.filter(user=user, pin=pin, interaction_type=interaction_type).exists():
            print(f"Interaction {interaction_type} already exists for {user.username} on pin {pin.id}")
            continue
        
        # Create the interaction
        interaction = PinInteraction.objects.create(
            user=user,
            pin=pin,
            interaction_type=interaction_type,
        )
        
        print(f"Created interaction: {user.username} {interaction_type} pin {pin.id}")
    
    # Create trending areas
    print("Creating trending areas...")
    for location in LOCATIONS:
        lng, lat = location
        
        # Check if area already exists
        if TrendingArea.objects.filter(center=Point(lng, lat)).exists():
            print(f"Trending area at {lng:.2f}, {lat:.2f} already exists")
            continue
        
        # Create the area
        area = TrendingArea.objects.create(
            name=f"Trending Area near {lng:.2f}, {lat:.2f}",
            center=Point(lng, lat),
            radius=random.choice([500, 800, 1000]),
            pin_count=random.randint(5, 20),
            top_genres=["Rock", "Pop", "Hip Hop"],
        )
        
        print(f"Created trending area: {area.name}")
    
    print("\nSample data generation complete!")
    print(f"Total users: {User.objects.count()}")
    print(f"Total pins: {Pin.objects.count()}")
    print(f"Total interactions: {PinInteraction.objects.count()}")
    print(f"Total friend connections: {Friend.objects.count()}")
    print(f"Total trending areas: {TrendingArea.objects.count()}")

except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc() 