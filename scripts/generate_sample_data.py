#!/usr/bin/env python
"""
Script to generate sample data for BOPMaps development.
This creates users, pins, interactions, and other related data.

Usage:
    python manage.py shell < scripts/generate_sample_data.py
"""

import os
import sys
import random
import json
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.db import transaction, models

from users.models import User
from pins.models import Pin, PinInteraction
from friends.models import Friend
from music.models import MusicService, Genre, RecentTrack
from gamification.models import Achievement, PinSkin, UserAchievement
from geo.models import TrendingArea, UserLocation

# Ensure script can be run directly from command line
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bopmaps.settings')

print("Starting sample data generation for BOPMaps...")

# Configuration
NUM_USERS = 50
NUM_PINS = 200
NUM_FRIEND_CONNECTIONS = 100
NUM_PIN_INTERACTIONS = 500
GENRES = [
    "Rock", "Pop", "Hip Hop", "R&B", "Country", "Electronic", "Jazz", 
    "Classical", "Folk", "Reggae", "Blues", "Metal", "Punk", "Indie", 
    "K-Pop", "Latin", "Gospel", "Soundtrack", "World", "New Age"
]

# Sample locations (coordinates for major cities)
LOCATIONS = [
    # City centers in format: (longitude, latitude)
    # New York
    (-73.9857, 40.7484),
    # Los Angeles
    (-118.2437, 34.0522),
    # Chicago
    (-87.6298, 41.8781),
    # Miami
    (-80.1918, 25.7617),
    # Austin
    (-97.7431, 30.2672),
    # San Francisco
    (-122.4194, 37.7749),
    # Seattle
    (-122.3321, 47.6062),
    # London
    (-0.1278, 51.5074),
    # Tokyo
    (139.6917, 35.6895),
    # Sydney
    (151.2093, -33.8688),
]

# Sample data helpers
def get_random_location(base_location=None, radius_km=5):
    """Get a random location, optionally near a base location"""
    if base_location:
        # Add some randomness to the base location (approximately within radius_km)
        lng, lat = base_location
        # 0.01 degrees is roughly 1km (this is an approximation)
        factor = radius_km * 0.01
        lng_offset = random.uniform(-factor, factor)
        lat_offset = random.uniform(-factor, factor)
        return (lng + lng_offset, lat + lat_offset)
    else:
        # Return a random location from our predefined list
        return random.choice(LOCATIONS)

def create_users(num_users):
    """Create sample users"""
    print(f"Creating {num_users} sample users...")
    users = []
    
    # Ensure we always have our admin user
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
    
    # Create regular users
    for i in range(1, num_users + 1):
        username = f"user{i}"
        email = f"user{i}@example.com"
        
        # Skip if the user already exists
        if User.objects.filter(username=username).exists():
            continue
            
        user = User.objects.create_user(
            username=username,
            email=email,
            password="password123",
            first_name=f"First{i}",
            last_name=f"Last{i}",
            bio=f"This is the bio for user {i}. They love music and sharing pins!",
            date_of_birth=timezone.now().date() - timedelta(days=random.randint(7000, 15000)),
        )
        
        # Set a random location
        lng, lat = get_random_location()
        user.location = Point(lng, lat)
        
        # Set random music service connections
        user.spotify_connected = random.choice([True, False])
        user.apple_music_connected = random.choice([True, False])
        user.soundcloud_connected = random.choice([True, False])
        
        # Set random stats
        user.pins_created = random.randint(0, 20)
        user.pins_collected = random.randint(0, 50)
        
        user.save()
        users.append(user)
        
    return users

def create_pin_skins():
    """Create sample pin skins"""
    print("Creating pin skins...")
    skins = []
    
    skin_data = [
        {"name": "Default", "description": "The default pin skin", "is_premium": False},
        {"name": "Gold", "description": "A shiny gold pin", "is_premium": True},
        {"name": "Neon", "description": "A bright neon-colored pin", "is_premium": True},
        {"name": "Vintage", "description": "A retro vinyl record style pin", "is_premium": True},
        {"name": "Star", "description": "A star-shaped pin", "is_premium": False},
        {"name": "Note", "description": "A musical note pin", "is_premium": False},
    ]
    
    for data in skin_data:
        skin, created = PinSkin.objects.get_or_create(
            name=data["name"],
            defaults={
                "description": data["description"],
                "is_premium": data["is_premium"],
                # Note: real images would be needed for a production environment
            }
        )
        skins.append(skin)
        
    return skins

def create_achievements():
    """Create sample achievements"""
    print("Creating achievements...")
    achievements = []
    
    achievement_data = [
        {
            "name": "First Pin", 
            "description": "Created your first pin", 
            "criteria": {"pins_created": 1}
        },
        {
            "name": "Pin Collector", 
            "description": "Collected 10 pins", 
            "criteria": {"pins_collected": 10}
        },
        {
            "name": "Music Explorer", 
            "description": "Collected pins from 5 different artists", 
            "criteria": {"unique_artists": 5}
        },
        {
            "name": "Social Butterfly", 
            "description": "Made 5 friends", 
            "criteria": {"friends_count": 5}
        },
        {
            "name": "Global Trotter", 
            "description": "Created pins in 3 different cities", 
            "criteria": {"unique_cities": 3}
        },
    ]
    
    for data in achievement_data:
        achievement, created = Achievement.objects.get_or_create(
            name=data["name"],
            defaults={
                "description": data["description"],
                "criteria": data["criteria"],
                # Assign a random skin as reward (except the first one)
                "reward_skin": PinSkin.objects.order_by("?").first() if data != achievement_data[0] else None
            }
        )
        achievements.append(achievement)
        
    return achievements

def create_genres():
    """Create music genres"""
    print("Creating music genres...")
    genres = []
    
    for genre_name in GENRES:
        genre, created = Genre.objects.get_or_create(name=genre_name)
        genres.append(genre)
        
    return genres

def create_friends(users, num_connections):
    """Create friend connections between users"""
    print(f"Creating {num_connections} friend connections...")
    friends = []
    
    for _ in range(num_connections):
        # Get two random users
        user1, user2 = random.sample(users, 2)
        
        # Check if connection already exists
        if Friend.objects.filter(
            (models.Q(requester=user1) & models.Q(recipient=user2)) |
            (models.Q(requester=user2) & models.Q(recipient=user1))
        ).exists():
            continue
            
        # Create a friend connection
        status = random.choice(['pending', 'accepted', 'rejected'])
        friend = Friend.objects.create(
            requester=user1,
            recipient=user2,
            status=status,
        )
        friends.append(friend)
        
    return friends

def create_pins(users, pin_skins, num_pins):
    """Create sample pins"""
    print(f"Creating {num_pins} pins...")
    pins = []
    
    # Sample track data (in real app, this would come from music service APIs)
    sample_tracks = [
        {
            "service": "spotify",
            "title": "Bohemian Rhapsody",
            "artist": "Queen",
            "album": "A Night at the Opera",
            "url": "https://open.spotify.com/track/7tFiyTwD0nx5a1eklYtX2J"
        },
        {
            "service": "spotify",
            "title": "Shape of You",
            "artist": "Ed Sheeran",
            "album": "÷",
            "url": "https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI3"
        },
        {
            "service": "apple",
            "title": "Billie Jean",
            "artist": "Michael Jackson",
            "album": "Thriller",
            "url": "https://music.apple.com/us/album/billie-jean/269572838?i=269573364"
        },
        {
            "service": "apple",
            "title": "Blinding Lights",
            "artist": "The Weeknd",
            "album": "After Hours",
            "url": "https://music.apple.com/us/album/blinding-lights/1499378108?i=1499378615"
        },
        {
            "service": "soundcloud",
            "title": "Indie Summer Mix",
            "artist": "Chill Artist",
            "album": "",
            "url": "https://soundcloud.com/chillartist/indie-summer-mix"
        },
        {
            "service": "spotify",
            "title": "Bad Guy",
            "artist": "Billie Eilish",
            "album": "When We All Fall Asleep, Where Do We Go?",
            "url": "https://open.spotify.com/track/2Fxmhks0bxGSBdJ92vM42m"
        },
        {
            "service": "apple",
            "title": "Uptown Funk",
            "artist": "Mark Ronson ft. Bruno Mars",
            "album": "Uptown Special",
            "url": "https://music.apple.com/us/album/uptown-funk-feat-bruno-mars/1440766980?i=1440767373"
        },
        {
            "service": "soundcloud",
            "title": "Lo-fi Beats to Study To",
            "artist": "Chill Producer",
            "album": "",
            "url": "https://soundcloud.com/chillproducer/lofi-beats-to-study-to"
        },
        {
            "service": "spotify",
            "title": "Someone Like You",
            "artist": "Adele",
            "album": "21",
            "url": "https://open.spotify.com/track/1T2mVxaYTLGwdXcjmtV0OT"
        },
        {
            "service": "apple",
            "title": "Sicko Mode",
            "artist": "Travis Scott",
            "album": "Astroworld",
            "url": "https://music.apple.com/us/album/sicko-mode/1421241217?i=1421241218"
        },
    ]
    
    # Create pins
    for _ in range(num_pins):
        # Get a random user and location
        user = random.choice(users)
        base_location = random.choice(LOCATIONS)
        lng, lat = get_random_location(base_location, 10)
        
        # Get a random track
        track = random.choice(sample_tracks)
        
        # Create a pin
        pin = Pin.objects.create(
            owner=user,
            location=Point(lng, lat),
            title=f"{user.username}'s {track['title']} pin",
            description=f"Check out this {track['title']} by {track['artist']}!",
            track_title=track['title'],
            track_artist=track['artist'],
            album=track['album'],
            track_url=track['url'],
            service=track['service'],
            skin=random.choice(pin_skins),
            rarity=random.choice(['common', 'common', 'common', 'uncommon', 'uncommon', 'rare', 'epic', 'legendary']),
            aura_radius=random.choice([50, 100, 150, 200, 250]),
            is_private=random.choice([True, False, False, False]),  # 25% chance of being private
            # Some pins might expire
            expiration_date=timezone.now() + timedelta(days=random.randint(1, 30)) if random.random() < 0.2 else None,
        )
        pins.append(pin)
        
    return pins

def create_pin_interactions(users, pins, num_interactions):
    """Create sample pin interactions"""
    print(f"Creating {num_interactions} pin interactions...")
    interactions = []
    
    for _ in range(num_interactions):
        # Get a random user and pin
        user = random.choice(users)
        pin = random.choice(pins)
        
        # Skip if user is the pin owner (they can't interact with their own pins)
        if pin.owner == user:
            continue
            
        # Get a random interaction type
        interaction_type = random.choice(['view', 'collect', 'like', 'share'])
        
        # Check if this interaction already exists
        if PinInteraction.objects.filter(user=user, pin=pin, interaction_type=interaction_type).exists():
            continue
            
        # Create the interaction
        interaction = PinInteraction.objects.create(
            user=user,
            pin=pin,
            interaction_type=interaction_type,
        )
        interactions.append(interaction)
        
        # Update user stats if appropriate
        if interaction_type == 'collect':
            user.pins_collected += 1
            user.save(update_fields=['pins_collected'])
            
    return interactions

def create_trending_areas():
    """Create sample trending areas"""
    print("Creating trending areas...")
    areas = []
    
    for location in LOCATIONS:
        lng, lat = location
        # Create a trending area
        area = TrendingArea.objects.create(
            name=f"Trending Area near {lng:.2f}, {lat:.2f}",
            center=Point(lng, lat),
            radius=random.choice([500, 800, 1000, 1500]),
            pin_count=random.randint(5, 50),
            top_genres=random.sample(GENRES, 3),
        )
        areas.append(area)
        
    return areas

def create_user_locations(users):
    """Create sample user location history"""
    print("Creating user location history...")
    locations = []
    
    for user in users:
        # Create between 1-5 location history entries for each user
        for _ in range(random.randint(1, 5)):
            if user.location:
                # Create a location near the user's current location
                base_lng, base_lat = user.location.x, user.location.y
                lng, lat = get_random_location((base_lng, base_lat), 3)
                
                # Create the location entry
                location = UserLocation.objects.create(
                    user=user,
                    location=Point(lng, lat),
                    # Random timestamp in the past week
                    timestamp=timezone.now() - timedelta(days=random.randint(0, 7)),
                )
                locations.append(location)
                
    return locations

def create_user_achievements(users, achievements):
    """Assign random achievements to users"""
    print("Creating user achievements...")
    user_achievements = []
    
    for user in users:
        # Assign between 0-3 random achievements to each user
        for achievement in random.sample(achievements, random.randint(0, min(3, len(achievements)))):
            # Skip if the user already has this achievement
            if UserAchievement.objects.filter(user=user, achievement=achievement).exists():
                continue
                
            # Create the user achievement
            user_achievement = UserAchievement.objects.create(
                user=user,
                achievement=achievement,
                # Random completion date in the past month
                completed_at=timezone.now() - timedelta(days=random.randint(0, 30)),
                progress={"completed": True},
            )
            user_achievements.append(user_achievement)
            
    return user_achievements

def create_music_services(users):
    """Create sample music service connections"""
    print("Creating music service connections...")
    connections = []
    
    for user in users:
        services = []
        # Create connections based on the user's connected flags
        if user.spotify_connected:
            services.append("spotify")
        if user.apple_music_connected:
            services.append("apple")
        if user.soundcloud_connected:
            services.append("soundcloud")
            
        for service_type in services:
            # Skip if connection already exists
            if MusicService.objects.filter(user=user, service_type=service_type).exists():
                continue
                
            # Create a music service connection
            connection = MusicService.objects.create(
                user=user,
                service_type=service_type,
                access_token=f"sample_token_{user.username}_{service_type}",
                refresh_token=f"sample_refresh_{user.username}_{service_type}",
                expires_at=timezone.now() + timedelta(hours=random.randint(1, 24)),
            )
            connections.append(connection)
            
    return connections

def create_recent_tracks(users):
    """Create sample recent tracks"""
    print("Creating recent tracks...")
    tracks = []
    
    # Sample track data (in real app, this would come from music service APIs)
    sample_tracks = [
        {
            "title": "Bohemian Rhapsody",
            "artist": "Queen",
            "album": "A Night at the Opera",
            "album_art": "https://example.com/album_art.jpg",
        },
        {
            "title": "Shape of You",
            "artist": "Ed Sheeran",
            "album": "÷",
            "album_art": "https://example.com/album_art2.jpg",
        },
        {
            "title": "Billie Jean",
            "artist": "Michael Jackson",
            "album": "Thriller",
            "album_art": "https://example.com/album_art3.jpg",
        },
        {
            "title": "Blinding Lights",
            "artist": "The Weeknd",
            "album": "After Hours",
            "album_art": "https://example.com/album_art4.jpg",
        },
        {
            "title": "Bad Guy",
            "artist": "Billie Eilish",
            "album": "When We All Fall Asleep, Where Do We Go?",
            "album_art": "https://example.com/album_art5.jpg",
        },
    ]
    
    for user in users:
        # Skip users with no music service connections
        if not user.spotify_connected and not user.apple_music_connected and not user.soundcloud_connected:
            continue
            
        # Determine which services the user has
        services = []
        if user.spotify_connected:
            services.append("spotify")
        if user.apple_music_connected:
            services.append("apple")
        if user.soundcloud_connected:
            services.append("soundcloud")
            
        # Create between 1-10 recent tracks for each user
        for _ in range(random.randint(1, 10)):
            track_data = random.choice(sample_tracks)
            service = random.choice(services)
            
            # Create a recent track
            track = RecentTrack.objects.create(
                user=user,
                track_id=f"track_{random.randint(10000, 99999)}",
                title=track_data["title"],
                artist=track_data["artist"],
                album=track_data["album"],
                album_art=track_data["album_art"],
                service=service,
                played_at=timezone.now() - timedelta(hours=random.randint(1, 48)),
            )
            tracks.append(track)
            
    return tracks

@transaction.atomic
def generate_all_sample_data():
    """Generate all sample data in a transaction"""
    # Create base data
    users = create_users(NUM_USERS)
    pin_skins = create_pin_skins()
    achievements = create_achievements()
    genres = create_genres()
    
    # Create relationship data
    friends = create_friends(users, NUM_FRIEND_CONNECTIONS)
    pins = create_pins(users, pin_skins, NUM_PINS)
    pin_interactions = create_pin_interactions(users, pins, NUM_PIN_INTERACTIONS)
    trending_areas = create_trending_areas()
    user_locations = create_user_locations(users)
    user_achievements = create_user_achievements(users, achievements)
    music_services = create_music_services(users)
    recent_tracks = create_recent_tracks(users)
    
    print("\nSample data generation complete!")
    print(f"Created {len(users)} users")
    print(f"Created {len(pin_skins)} pin skins")
    print(f"Created {len(achievements)} achievements")
    print(f"Created {len(genres)} genres")
    print(f"Created {len(friends)} friend connections")
    print(f"Created {len(pins)} pins")
    print(f"Created {len(pin_interactions)} pin interactions")
    print(f"Created {len(trending_areas)} trending areas")
    print(f"Created {len(user_locations)} user locations")
    print(f"Created {len(user_achievements)} user achievements")
    print(f"Created {len(music_services)} music service connections")
    print(f"Created {len(recent_tracks)} recent tracks")

if __name__ == "__main__":
    generate_all_sample_data() 