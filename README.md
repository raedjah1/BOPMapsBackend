# 🎵 BOPMaps Backend Documentation

**Version:** 1.0  
**Lead Devs:** Jah, Mason, Eric, Isaiah, Danny  
**Stack:** Django REST Framework (Backend) • React (Frontend) • Spotify/Apple/Soundcloud APIs • Geolocation & Leaflet.js Maps

---

## 🌐 Project Overview
**BOPMaps** is a musical geocaching app that allows users to **drop music pins at physical locations**, discover new songs in real-world contexts, and build social experiences around music and space. The app merges **gamification**, **location-based discovery**, and **social listening**.

---

## 📋 Features

- **User Management:**
  - User registration and authentication
  - User profile management 
  - Friend system with request/accept workflow
  - Personalization through music preferences

- **Pin Management:**
  - Create and drop music pins at specific locations
  - Link pins to music streaming services (Spotify/Apple/Soundcloud)
  - View, collect, and interact with pins
  - Pin customization (skins, rarity levels)

- **Discovery:**
  - Geolocation-based music discovery
  - Filter pins by genre, artist, or popularity
  - Discover pins from friends and followed users
  - Trending music in specific areas

- **Social Features:**
  - Friend connections
  - Music sharing
  - Activity feeds
  - Location-based communities

- **Gamification:**
  - Pin collection system
  - Rarity tiers for pins
  - Customizable pin skins
  - Achievement system

- **Geolocation:**
  - Real-time location tracking
  - Aura-based proximity detection
  - Map visualization
  - Location-based notifications

---

## ⚙️ Backend Architecture

**Language & Framework:** Python 3.x + Django REST Framework  
**Database:** PostgreSQL with PostGIS extension  
**Hosting:** TBD (Heroku, Railway, or AWS likely)  
**Auth:** Token-based (JWT)  
**APIs Integrated:**
- Geolocation API
- Leaflet.js (Map frontend rendering)
- Spotify/Apple/Soundcloud APIs (for track embedding, sharing, streaming)

---

## 📱 High-Level System Design

```
                                   +-------------+
                                   |             |
                +----------------->+  Music APIs +<----------------+
                |                  |             |                 |
                |                  +-------------+                 |
                |                                                  |
                |                                                  |
+---------------v----------------+                 +---------------v----------------+
|                               |                 |                                |
|                               |                 |                                |
|        BOPMaps Backend        |<--------------->|        BOPMaps Frontend        |
|        (Django REST API)      |                 |        (React)                 |
|                               |                 |                                |
+---------------^----------------+                 +--------------------------------+
                |
                |
                |
+---------------v----------------+
|                               |
|        PostgreSQL DB          |
|        with PostGIS           |
|                               |
+-------------------------------+
```

---

## 📁 App Structure

```
BOPMapsBackend/
│
├── bopmaps/                # Core app configuration
│   ├── settings.py         # Django settings
│   ├── urls.py             # Main URL routing
│   ├── wsgi.py             # WSGI configuration
│
├── users/                  # User authentication and profiles
│   ├── models.py           # User models
│   ├── views.py            # User-related API views
│   ├── serializers.py      # User data serialization
│   ├── urls.py             # User endpoints routing
│
├── pins/                   # Music pin functionality
│   ├── models.py           # Pin and interaction models
│   ├── views.py            # Pin-related API views
│   ├── serializers.py      # Pin data serialization
│   ├── urls.py             # Pin endpoints routing
│
├── friends/                # Friend relationships and social features
│   ├── models.py           # Friend models
│   ├── views.py            # Friend-related API views
│   ├── serializers.py      # Friend data serialization
│   ├── urls.py             # Friend endpoints routing
│
├── music/                  # Music integration and API connections
│   ├── models.py           # Music data models
│   ├── views.py            # Music-related API views
│   ├── serializers.py      # Music data serialization
│   ├── urls.py             # Music endpoints routing
│   ├── connectors/         # Music API integration
│
├── gamification/           # Game elements and achievements
│   ├── models.py           # Gamification models
│   ├── views.py            # Game-related API views
│   ├── serializers.py      # Game data serialization
│   ├── urls.py             # Game endpoints routing
│
├── geo/                    # Geolocation services
│   ├── models.py           # Geo models
│   ├── views.py            # Location-based API views
│   ├── serializers.py      # Geo data serialization
│   ├── urls.py             # Geo endpoints routing
│   ├── utils.py            # Spatial calculation utilities
│
├── manage.py               # Django management script
└── requirements.txt        # Project dependencies
```

---

## 🔐 Authentication System

- **User Registration & Login**
  - Email/password registration
  - Social auth integration (optional)
  - Secure password hashing

- **JWT Authentication**
  - Token-based auth using Django REST Framework SimpleJWT
  - Refresh tokens for extended sessions
  - Token blacklisting for security

- **Permission Levels**
  - Standard users
  - Premium users (future expansion)
  - Admin users

---

## 🧠 Core Models

### 1. **User**
```python
class User(AbstractUser):
    email = models.EmailField(unique=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    location = models.PointField(geography=True, blank=True, null=True)
    last_active = models.DateTimeField(auto_now=True)
    favorite_genres = models.ManyToManyField('music.Genre', blank=True)
    spotify_connected = models.BooleanField(default=False)
    apple_music_connected = models.BooleanField(default=False)
    soundcloud_connected = models.BooleanField(default=False)
```

### 2. **Friend**
```python
class Friend(models.Model):
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friend_requests_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friend_requests_received')
    status = models.CharField(max_length=10, choices=[
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected')
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('requester', 'recipient')
```

### 3. **Pin**
```python
class Pin(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pins')
    location = models.PointField(geography=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    # Music data
    track_title = models.CharField(max_length=255)
    track_artist = models.CharField(max_length=255)
    album = models.CharField(max_length=255, blank=True, null=True)
    track_url = models.URLField()
    service = models.CharField(max_length=20, choices=[
        ('spotify', 'Spotify'),
        ('apple', 'Apple Music'),
        ('soundcloud', 'SoundCloud')
    ])
    
    # Customization & Gamification
    skin = models.ForeignKey('gamification.PinSkin', on_delete=models.SET_DEFAULT, default=1)
    rarity = models.CharField(max_length=20, choices=[
        ('common', 'Common'),
        ('uncommon', 'Uncommon'),
        ('rare', 'Rare'),
        ('epic', 'Epic'),
        ('legendary', 'Legendary')
    ], default='common')
    
    # Discovery
    aura_radius = models.IntegerField(default=50)  # meters
    is_private = models.BooleanField(default=False)
    expiration_date = models.DateTimeField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 4. **PinInteraction**
```python
class PinInteraction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pin_interactions')
    pin = models.ForeignKey(Pin, on_delete=models.CASCADE, related_name='interactions')
    interaction_type = models.CharField(max_length=20, choices=[
        ('view', 'Viewed'),
        ('collect', 'Collected'),
        ('like', 'Liked'),
        ('share', 'Shared')
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'pin', 'interaction_type')
```

### 5. **PinSkin**
```python
class PinSkin(models.Model):
    name = models.CharField(max_length=50)
    image = models.ImageField(upload_to='pin_skins/')
    description = models.TextField(blank=True, null=True)
    is_premium = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

---

## 🔄 Serializers

Standard Django REST Framework serializers for each model with appropriate depth and relational representation:

### User Serializer
```python
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'profile_pic', 'bio', 'date_joined', 'last_active')
        read_only_fields = ('id', 'date_joined', 'last_active')
```

### Pin Serializer
```python
class PinSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    distance = serializers.SerializerMethodField()
    
    class Meta:
        model = Pin
        fields = '__all__'
        
    def get_distance(self, obj):
        user_location = self.context.get('user_location')
        if user_location:
            # Calculate distance between pin and user
            return calculate_distance(user_location, obj.location)
        return None
```

Additional serializers for Friend, PinInteraction, and other models to facilitate API responses.

---

## 🧩 Core API Endpoints

### 🔐 Authentication
```
POST   /api/auth/register/            # Register new user
POST   /api/auth/login/               # Log in
POST   /api/auth/token/refresh/       # Refresh JWT token
POST   /api/auth/logout/              # Log out (token blacklist)
```

### 👤 Users
```
GET    /api/users/me/                 # Get current user profile
PUT    /api/users/me/                 # Update current user profile
GET    /api/users/{id}/               # Get specific user profile
PATCH  /api/users/connect/{service}/  # Connect to music service (Spotify, etc.)
```

### 👫 Friends
```
GET    /api/friends/                  # List friends
POST   /api/friends/request/{id}/     # Send friend request
POST   /api/friends/accept/{id}/      # Accept friend request
POST   /api/friends/reject/{id}/      # Reject friend request
DELETE /api/friends/{id}/             # Remove friend
```

### 📍 Pins
```
GET    /api/pins/                     # Get pins (filtered by proximity, etc.)
POST   /api/pins/                     # Create new pin
GET    /api/pins/{id}/                # Get specific pin details
PATCH  /api/pins/{id}/                # Update pin details
DELETE /api/pins/{id}/                # Delete pin
POST   /api/pins/{id}/interact/       # Record an interaction with a pin
```

### 🎵 Music
```
GET    /api/music/search/             # Search tracks from connected services
GET    /api/music/recent/             # Get recently played tracks
GET    /api/music/services/status/    # Check connected music services status
```

### 🏆 Gamification
```
GET    /api/game/skins/               # Get available pin skins
GET    /api/game/achievements/        # Get user achievements
GET    /api/game/stats/               # Get user stats (pins dropped, collected, etc.)
```

### 🌍 Geo
```
POST   /api/geo/nearby/               # Get nearby pins based on location
GET    /api/geo/trending/             # Get trending areas with many pins
GET    /api/geo/heatmap/              # Get pin density data for heatmap display
```

---

## 📍 Geolocation and Aura Logic

The core location-based features of BOPMaps rely on spatial database capabilities:

### Location Storage
- User and Pin positions stored using Django's `PointField` with PostGIS
- Coordinates saved in standard WGS84 format (latitude/longitude)

### Pin Discovery Algorithm
```python
# Simplified example of proximity-based pin discovery
from django.contrib.gis.measure import D
from django.contrib.gis.geos import Point

def get_nearby_pins(latitude, longitude, radius_m=1000):
    user_location = Point(longitude, latitude, srid=4326)
    
    # Filter pins by distance
    pins = Pin.objects.filter(
        location__distance_lte=(user_location, D(m=radius_m))
    ).annotate(
        distance=Distance('location', user_location)
    ).order_by('distance')
    
    return pins
```

### Aura Mechanics
- Each pin has an `aura_radius` defining its discovery radius
- Users must be physically within this radius to interact with a pin
- Verification happens on both client and server side for security

### Spatial Indexing
- PostGIS spatial indexes optimize location-based queries
- Fast retrieval of pins within given radius or bounding box

---

## 📱 Notifications

Handled via Firebase Cloud Messaging (FCM) for push notifications:

- **Proximity Alerts:** When a user comes near a pin
- **Friend Activities:** When friends drop pins nearby
- **Collection Reminders:** Reminders for uncollected nearby pins
- **New Friend Requests:** Notifications for social interactions

Implementation using Django signals to trigger notifications on relevant events:

```python
@receiver(post_save, sender=Pin)
def notify_nearby_users(sender, instance, created, **kwargs):
    if created:
        # Find users within pin's aura radius
        nearby_users = User.objects.filter(
            location__distance_lte=(instance.location, D(m=instance.aura_radius * 2))
        )
        
        # Send notification to each nearby user
        for user in nearby_users:
            if user != instance.owner:
                send_push_notification(
                    user.device_token,
                    title="New music dropped nearby!",
                    body=f"{instance.owner.username} dropped '{instance.track_title}'",
                    data={
                        "pin_id": instance.id,
                        "lat": instance.location.y,
                        "lng": instance.location.x
                    }
                )
```

---

## 🪙 Gamification Engine

### Pin Collection System
- Users "collect" pins to build their music library
- Collection history tracked in `PinInteraction` model
- Achievements unlocked based on collection milestones

### Rarity System
```python
def determine_pin_rarity():
    """Algorithm to determine pin rarity based on several factors"""
    random_factor = random.random()
    
    if random_factor < 0.60:   return 'common'     # 60% chance
    if random_factor < 0.85:   return 'uncommon'   # 25% chance
    if random_factor < 0.95:   return 'rare'       # 10% chance
    if random_factor < 0.99:   return 'epic'       # 4% chance
    return 'legendary'                             # 1% chance
```

### Pin Skins
- Visual customizations for pins on map
- Mix of free and premium skins
- Special skins for achievements or events

### Achievement System
- Track user progress across various activities
- Award badges and special skins for completions
- Example achievements:
  - "Globetrotter": Collect pins in 5+ different cities
  - "Genremaster": Collect pins from 10 different music genres
  - "Local Legend": Drop 50+ pins in one area

---

## 🔧 Development Setup

### Prerequisites

- Python 3.8+
- PostgreSQL with PostGIS extension
- Redis (optional, for caching and background tasks)

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/BOPMapsBackend.git
cd BOPMapsBackend
```

### Step 2: Set Up the Environment

There are two options for setting up your development environment:

#### Option 1: Automated Setup (Recommended)

```bash
# Make the setup script executable
chmod +x setup.sh

# Run the setup script
./setup.sh
```

The setup script will:
- Create and activate a virtual environment
- Install dependencies
- Set up environment variables
- Configure the database
- Run migrations
- Create a superuser (if needed)
- Set up static files

#### Option 2: Manual Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file from the example:
```bash
cp .env.example .env
# Edit .env with your settings
```

4. Create a PostgreSQL database with PostGIS:
```bash
psql -U postgres
CREATE DATABASE bopmaps;
\c bopmaps
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_topology;
\q
```

5. Run migrations:
```bash
python manage.py migrate
```

6. Create a superuser:
```bash
python manage.py createsuperuser
```

7. Collect static files:
```bash
python manage.py collectstatic
```

### Step 3: Run the Development Server

```bash
python manage.py runserver
```

Access the API at http://localhost:8000/api/

Access the admin interface at http://localhost:8000/admin/

## API Documentation

- Interactive API documentation: http://localhost:8000/api/schema/swagger-ui/
- ReDoc API documentation: http://localhost:8000/api/schema/redoc/
- Detailed API documentation: See `API_DOCUMENTATION.md`

## Testing

Run the test suite:

```bash
# Run all tests
python manage.py test

# Run tests with specific settings
python manage.py test --settings=bopmaps.test_settings
```

## Project Structure

```
BOPMapsBackend/
├── bopmaps/              # Project configuration
├── users/                # User management app
├── pins/                 # Music pins app
├── friends/              # Friend connections app
├── music/                # Music integration app
├── gamification/         # Achievements and rewards app
├── geo/                  # Geospatial services app
└── manage.py             # Django management script
```

## License

[MIT License](LICENSE) 