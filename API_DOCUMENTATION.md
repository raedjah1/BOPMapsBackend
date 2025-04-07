# BOPMaps API Documentation

This document provides a comprehensive overview of the BOPMaps REST API, including endpoints, request/response formats, and authentication requirements.

**Base URL**: `https://api.bopmaps.com` (Production) or `http://localhost:8000` (Development)

**API Version**: v1

## Table of Contents

1. [Authentication](#authentication)
2. [Users](#users)
3. [Pins](#pins)
4. [Friends](#friends)
5. [Music](#music)
6. [Gamification](#gamification)
7. [Geo](#geo)
8. [Error Handling](#error-handling)

---

## Authentication

BOPMaps uses JWT (JSON Web Tokens) for authentication. Include the token in the Authorization header for authenticated requests.

### Register User

```
POST /api/auth/register/
```

**Request Body**:
```json
{
  "username": "user123",
  "email": "user@example.com",
  "password": "securepassword",
  "first_name": "John",
  "last_name": "Doe"
}
```

**Response**:
```json
{
  "id": 1,
  "username": "user123",
  "email": "user@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Login

```
POST /api/auth/login/
```

**Request Body**:
```json
{
  "username": "user123",
  "password": "securepassword"
}
```

**Response**:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com"
  }
}
```

### Refresh Token

```
POST /api/auth/token/refresh/
```

**Request Body**:
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response**:
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Logout

```
POST /api/auth/logout/
```

**Request Body**:
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response**:
```json
{
  "message": "Successfully logged out"
}
```

---

## Users

### Get Current User Profile

```
GET /api/users/me/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "id": 1,
  "username": "user123",
  "email": "user@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "profile_pic": "https://api.bopmaps.com/media/profile_pics/user123.jpg",
  "bio": "Music enthusiast",
  "location": {
    "type": "Point",
    "coordinates": [40.7128, -74.0060]
  },
  "date_joined": "2023-01-15T12:00:00Z",
  "last_active": "2023-06-20T15:30:00Z",
  "favorite_genres": [
    {
      "id": 1,
      "name": "Rock"
    },
    {
      "id": 3,
      "name": "Hip-Hop"
    }
  ],
  "spotify_connected": true,
  "apple_music_connected": false,
  "soundcloud_connected": false
}
```

### Update Current User Profile

```
PUT /api/users/me/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Request Body**:
```json
{
  "first_name": "Johnny",
  "last_name": "Doe",
  "bio": "Music enthusiast and traveler",
  "favorite_genres": [1, 3, 5]
}
```

**Response**:
```json
{
  "id": 1,
  "username": "user123",
  "email": "user@example.com",
  "first_name": "Johnny",
  "last_name": "Doe",
  "profile_pic": "https://api.bopmaps.com/media/profile_pics/user123.jpg",
  "bio": "Music enthusiast and traveler",
  "location": {
    "type": "Point",
    "coordinates": [40.7128, -74.0060]
  },
  "date_joined": "2023-01-15T12:00:00Z",
  "last_active": "2023-06-20T15:30:00Z",
  "favorite_genres": [
    {
      "id": 1,
      "name": "Rock"
    },
    {
      "id": 3,
      "name": "Hip-Hop"
    },
    {
      "id": 5,
      "name": "Electronic"
    }
  ],
  "spotify_connected": true,
  "apple_music_connected": false,
  "soundcloud_connected": false
}
```

### Get User Profile

```
GET /api/users/{id}/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "id": 2,
  "username": "jane_smith",
  "first_name": "Jane",
  "last_name": "Smith",
  "profile_pic": "https://api.bopmaps.com/media/profile_pics/jane_smith.jpg",
  "bio": "Jazz lover",
  "is_friend": true,
  "friend_status": "accepted"
}
```

### Connect Music Service

```
PATCH /api/users/connect/{service}/
```

Where `{service}` is one of: `spotify`, `apple`, or `soundcloud`

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Request Body**:
```json
{
  "access_token": "spotify_access_token",
  "refresh_token": "spotify_refresh_token"
}
```

**Response**:
```json
{
  "message": "Successfully connected to Spotify",
  "spotify_connected": true
}
```

---

## Pins

### Get Pins

```
GET /api/pins/
```

**Query Parameters**:
- `lat` (float): User's latitude
- `lng` (float): User's longitude
- `radius` (int, optional): Search radius in meters (default: 1000)
- `page` (int, optional): Page number for pagination
- `page_size` (int, optional): Results per page (default: 20)

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "count": 125,
  "next": "http://api.bopmaps.com/api/pins/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "owner": {
        "id": 3,
        "username": "music_dropper",
        "profile_pic": "https://api.bopmaps.com/media/profile_pics/music_dropper.jpg"
      },
      "title": "Chill Vibes",
      "description": "Perfect spot for this track",
      "location": {
        "type": "Point",
        "coordinates": [40.7135, -74.0046]
      },
      "track_title": "Summer Nights",
      "track_artist": "Chill Artist",
      "album": "Relaxation",
      "track_url": "https://open.spotify.com/track/1234567890",
      "service": "spotify",
      "skin": {
        "id": 2,
        "name": "Neon",
        "image": "https://api.bopmaps.com/media/pin_skins/neon.png"
      },
      "rarity": "rare",
      "aura_radius": 50,
      "created_at": "2023-06-15T11:30:00Z",
      "updated_at": "2023-06-15T11:30:00Z",
      "distance": 150.45,
      "interaction_status": {
        "viewed": true,
        "collected": false,
        "liked": true
      }
    },
    // More pins...
  ]
}
```

### Create Pin

```
POST /api/pins/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Request Body**:
```json
{
  "title": "Morning Commute",
  "description": "This track makes my morning commute better",
  "lat": 40.7128,
  "lng": -74.0060,
  "track_title": "Happy Day",
  "track_artist": "Good Vibes",
  "album": "Positivity",
  "track_url": "https://open.spotify.com/track/0987654321",
  "service": "spotify",
  "skin_id": 1,
  "aura_radius": 75,
  "is_private": false
}
```

**Response**:
```json
{
  "id": 10,
  "owner": {
    "id": 1,
    "username": "user123",
    "profile_pic": "https://api.bopmaps.com/media/profile_pics/user123.jpg"
  },
  "title": "Morning Commute",
  "description": "This track makes my morning commute better",
  "location": {
    "type": "Point",
    "coordinates": [40.7128, -74.0060]
  },
  "track_title": "Happy Day",
  "track_artist": "Good Vibes",
  "album": "Positivity",
  "track_url": "https://open.spotify.com/track/0987654321",
  "service": "spotify",
  "skin": {
    "id": 1,
    "name": "Classic",
    "image": "https://api.bopmaps.com/media/pin_skins/classic.png"
  },
  "rarity": "common",
  "aura_radius": 75,
  "is_private": false,
  "created_at": "2023-06-20T08:45:00Z",
  "updated_at": "2023-06-20T08:45:00Z"
}
```

### Get Pin Details

```
GET /api/pins/{id}/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "id": 10,
  "owner": {
    "id": 1,
    "username": "user123",
    "profile_pic": "https://api.bopmaps.com/media/profile_pics/user123.jpg"
  },
  "title": "Morning Commute",
  "description": "This track makes my morning commute better",
  "location": {
    "type": "Point",
    "coordinates": [40.7128, -74.0060]
  },
  "track_title": "Happy Day",
  "track_artist": "Good Vibes",
  "album": "Positivity",
  "track_url": "https://open.spotify.com/track/0987654321",
  "service": "spotify",
  "skin": {
    "id": 1,
    "name": "Classic",
    "image": "https://api.bopmaps.com/media/pin_skins/classic.png"
  },
  "rarity": "common",
  "aura_radius": 75,
  "is_private": false,
  "created_at": "2023-06-20T08:45:00Z",
  "updated_at": "2023-06-20T08:45:00Z",
  "interaction_status": {
    "viewed": true,
    "collected": false,
    "liked": false
  },
  "interactions_count": {
    "views": 45,
    "collects": 12,
    "likes": 8
  }
}
```

### Update Pin

```
PATCH /api/pins/{id}/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Request Body**:
```json
{
  "title": "Updated Title",
  "description": "Updated description",
  "skin_id": 3
}
```

**Response**:
```json
{
  "id": 10,
  "title": "Updated Title",
  "description": "Updated description",
  "skin": {
    "id": 3,
    "name": "Retro",
    "image": "https://api.bopmaps.com/media/pin_skins/retro.png"
  },
  // Other pin details...
}
```

### Delete Pin

```
DELETE /api/pins/{id}/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "message": "Pin successfully deleted"
}
```

### Record Pin Interaction

```
POST /api/pins/{id}/interact/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Request Body**:
```json
{
  "interaction_type": "collect",
  "lat": 40.7128,
  "lng": -74.0060
}
```

**Response**:
```json
{
  "message": "Interaction recorded successfully",
  "interaction": {
    "id": 156,
    "user": 1,
    "pin": 10,
    "interaction_type": "collect",
    "created_at": "2023-06-20T16:30:00Z"
  }
}
```

---

## Friends

### List Friends

```
GET /api/friends/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "friends": [
    {
      "id": 2,
      "username": "jane_smith",
      "first_name": "Jane",
      "last_name": "Smith",
      "profile_pic": "https://api.bopmaps.com/media/profile_pics/jane_smith.jpg",
      "status": "accepted",
      "since": "2023-03-15T10:20:00Z"
    },
    // More friends...
  ],
  "pending_sent": [
    {
      "id": 3,
      "username": "music_dropper",
      "first_name": "Music",
      "last_name": "Dropper",
      "profile_pic": "https://api.bopmaps.com/media/profile_pics/music_dropper.jpg",
      "status": "pending",
      "requested_at": "2023-06-18T14:25:00Z"
    }
  ],
  "pending_received": [
    {
      "id": 4,
      "username": "new_friend",
      "first_name": "New",
      "last_name": "Friend",
      "profile_pic": "https://api.bopmaps.com/media/profile_pics/new_friend.jpg",
      "status": "pending",
      "requested_at": "2023-06-19T09:15:00Z"
    }
  ]
}
```

### Send Friend Request

```
POST /api/friends/request/{id}/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "message": "Friend request sent to new_friend",
  "status": "pending",
  "requested_at": "2023-06-20T11:30:00Z"
}
```

### Accept Friend Request

```
POST /api/friends/accept/{id}/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "message": "Friend request from new_friend accepted",
  "status": "accepted",
  "accepted_at": "2023-06-20T12:15:00Z"
}
```

### Reject Friend Request

```
POST /api/friends/reject/{id}/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "message": "Friend request from new_friend rejected",
  "status": "rejected",
  "rejected_at": "2023-06-20T12:20:00Z"
}
```

### Remove Friend

```
DELETE /api/friends/{id}/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "message": "Friendship with jane_smith removed"
}
```

---

## Music

### Search Tracks

```
GET /api/music/search/
```

**Query Parameters**:
- `q` (string): Search query
- `service` (string, optional): Specific service to search (spotify, apple, soundcloud)
- `limit` (int, optional): Maximum number of results (default: 20)

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "results": [
    {
      "id": "spotify:track:1234567890",
      "title": "Summer Nights",
      "artist": "Chill Artist",
      "album": "Relaxation",
      "album_art": "https://i.scdn.co/image/ab67616d0000b273...",
      "duration_ms": 234000,
      "preview_url": "https://p.scdn.co/mp3-preview/...",
      "service": "spotify"
    },
    // More tracks...
  ]
}
```

### Recent Tracks

```
GET /api/music/recent/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "recent_tracks": [
    {
      "id": "spotify:track:0987654321",
      "title": "Happy Day",
      "artist": "Good Vibes",
      "album": "Positivity",
      "album_art": "https://i.scdn.co/image/ab67616d0000b273...",
      "played_at": "2023-06-20T08:30:00Z",
      "service": "spotify"
    },
    // More tracks...
  ]
}
```

### Music Services Status

```
GET /api/music/services/status/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "spotify": {
    "connected": true,
    "username": "spotify_username",
    "expires_at": "2023-06-21T10:30:00Z"
  },
  "apple_music": {
    "connected": false
  },
  "soundcloud": {
    "connected": false
  }
}
```

---

## Gamification

### Get Available Pin Skins

```
GET /api/game/skins/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "available_skins": [
    {
      "id": 1,
      "name": "Classic",
      "description": "The original BOPMaps pin",
      "image": "https://api.bopmaps.com/media/pin_skins/classic.png",
      "is_premium": false,
      "created_at": "2023-01-01T00:00:00Z"
    },
    {
      "id": 2,
      "name": "Neon",
      "description": "A vibrant neon pin that glows on the map",
      "image": "https://api.bopmaps.com/media/pin_skins/neon.png",
      "is_premium": false,
      "created_at": "2023-01-15T00:00:00Z"
    },
    // More skins...
  ],
  "locked_skins": [
    {
      "id": 5,
      "name": "Gold",
      "description": "An exclusive gold pin for premium users",
      "image": "https://api.bopmaps.com/media/pin_skins/gold.png",
      "is_premium": true,
      "created_at": "2023-03-01T00:00:00Z",
      "unlock_condition": "Premium subscription required"
    },
    // More locked skins...
  ]
}
```

### Get User Achievements

```
GET /api/game/achievements/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "completed": [
    {
      "id": 1,
      "name": "First Drop",
      "description": "Drop your first pin",
      "icon": "https://api.bopmaps.com/media/achievements/first_drop.png",
      "completed_at": "2023-02-10T15:45:00Z",
      "reward": {
        "type": "skin",
        "skin_id": 3,
        "skin_name": "Retro"
      }
    },
    // More completed achievements...
  ],
  "in_progress": [
    {
      "id": 5,
      "name": "Globetrotter",
      "description": "Drop pins in 5 different cities",
      "icon": "https://api.bopmaps.com/media/achievements/globetrotter.png",
      "progress": {
        "current": 3,
        "target": 5,
        "percentage": 60
      },
      "reward": {
        "type": "skin",
        "skin_id": 8,
        "skin_name": "World"
      }
    },
    // More in-progress achievements...
  ]
}
```

### Get User Stats

```
GET /api/game/stats/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "pins": {
    "dropped": 42,
    "collected": 158,
    "liked": 75
  },
  "rarities": {
    "common": 28,
    "uncommon": 10,
    "rare": 3,
    "epic": 1,
    "legendary": 0
  },
  "genres": {
    "Rock": 15,
    "Pop": 8,
    "Hip-Hop": 12,
    "Electronic": 7
  },
  "activity": {
    "days_active": 65,
    "longest_streak": 12,
    "current_streak": 3
  }
}
```

---

## Geo

### Nearby Pins

```
POST /api/geo/nearby/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Request Body**:
```json
{
  "lat": 40.7128,
  "lng": -74.0060,
  "radius": 500,
  "limit": 50
}
```

**Response**:
```json
{
  "count": 12,
  "pins": [
    {
      "id": 15,
      "title": "Lunch Break Tunes",
      "owner": {
        "id": 3,
        "username": "music_dropper"
      },
      "location": {
        "type": "Point",
        "coordinates": [40.7135, -74.0046]
      },
      "distance": 125.7,
      "track_title": "Afternoon Delight",
      "track_artist": "Chill Vibes",
      "service": "spotify",
      "rarity": "uncommon",
      "created_at": "2023-06-15T12:30:00Z"
    },
    // More pins...
  ]
}
```

### Trending Areas

```
GET /api/geo/trending/
```

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "trending_areas": [
    {
      "name": "Central Park",
      "center": {
        "type": "Point",
        "coordinates": [40.7812, -73.9665]
      },
      "pin_count": 45,
      "radius": 800,
      "top_genres": ["Pop", "Rock", "Hip-Hop"]
    },
    // More trending areas...
  ]
}
```

### Heatmap Data

```
GET /api/geo/heatmap/
```

**Query Parameters**:
- `sw_lat` (float): Southwest latitude of the map viewport
- `sw_lng` (float): Southwest longitude of the map viewport
- `ne_lat` (float): Northeast latitude of the map viewport
- `ne_lng` (float): Northeast longitude of the map viewport

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "points": [
    {
      "lat": 40.7128,
      "lng": -74.0060,
      "weight": 10
    },
    {
      "lat": 40.7135,
      "lng": -74.0046,
      "weight": 5
    },
    // More points...
  ]
}
```

---

## Error Handling

### Common Error Codes

- **400 Bad Request**: Invalid parameters or request format
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource not found
- **409 Conflict**: Resource conflict
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Server-side error

### Error Response Format

```json
{
  "error": {
    "code": "invalid_request",
    "message": "The request contains invalid parameters",
    "details": {
      "field_name": ["Error details"]
    }
  }
}
```

### Validation Error Example

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid data provided",
    "details": {
      "email": ["Enter a valid email address."],
      "password": ["This password is too short. It must contain at least 8 characters."]
    }
  }
}
``` 