# BOPMaps API Documentation

This document provides an overview of the API endpoints available in the BOPMaps application.

For a more detailed and interactive documentation, you can use the Swagger UI at `/api/schema/swagger-ui/` when the server is running.

## Table of Contents

1. [Authentication](#authentication)
2. [Users](#users)
3. [Pins](#pins)
4. [Pin Interactions](#pin-interactions)
5. [Friends](#friends)
6. [Music Integration](#music-integration)
7. [Gamification](#gamification)
8. [Geo Services](#geo-services)

## Authentication

BOPMaps uses JWT (JSON Web Tokens) for authentication. All authenticated endpoints require a valid access token.

### Get Access Token

**Endpoint:** `POST /api/users/auth/token/`

**Description:** Obtain JWT access and refresh tokens.

**Request:**
```json
{
  "username": "your_username",
  "password": "your_password"
}
```

**Response:**
```json
{
  "refresh": "your_refresh_token",
  "access": "your_access_token",
  "user": {
    "id": "user_id",
    "username": "your_username",
    "email": "your_email",
    "profile_pic": "profile_image_url",
    "last_active": "2023-04-06T12:34:56Z",
    "spotify_connected": false,
    "apple_music_connected": false,
    "soundcloud_connected": false
  }
}
```

### Refresh Token

**Endpoint:** `POST /api/users/auth/token/refresh/`

**Description:** Get a new access token using your refresh token.

**Request:**
```json
{
  "refresh": "your_refresh_token"
}
```

**Response:**
```json
{
  "access": "new_access_token"
}
```

### Verify Token

**Endpoint:** `POST /api/token/verify/`

**Description:** Verify that a token is valid.

**Request:**
```json
{
  "token": "your_token"
}
```

**Response:**
- `200 OK` if the token is valid
- `401 Unauthorized` if the token is invalid

### Register

**Endpoint:** `POST /api/users/auth/register/`

**Description:** Register a new user.

**Request:**
```json
{
  "username": "new_username",
  "email": "user@example.com",
  "password": "secure_password",
  "password_confirm": "secure_password",
  "profile_pic": "image_file",  // Optional
  "bio": "About me"  // Optional
}
```

**Response:**
```json
{
  "message": "User registered successfully",
  "user": {
    "id": "user_id",
    "username": "new_username",
    "email": "user@example.com",
    "profile_pic": "profile_image_url",
    "bio": "About me",
    "last_active": "2023-04-06T12:34:56Z"
  },
  "tokens": {
    "refresh": "refresh_token",
    "access": "access_token"
  }
}
```

### Logout

**Endpoint:** `POST /api/users/auth/logout/`

**Description:** Invalidate refresh token (logout).

**Request:**
```json
{
  "refresh": "your_refresh_token"
}
```

**Response:**
```json
{
  "message": "Logout successful"
}
```

## Users

### Get Current User

**Endpoint:** `GET /api/users/me/`

**Description:** Get the current authenticated user's profile.

**Response:**
```json
{
  "id": "user_id",
  "username": "your_username",
  "email": "your_email",
  "profile_pic": "profile_image_url",
  "bio": "About me",
  "location": {
    "type": "Point",
    "coordinates": [longitude, latitude]
  },
  "last_active": "2023-04-06T12:34:56Z",
  "spotify_connected": false,
  "apple_music_connected": false,
  "soundcloud_connected": false
}
```

### Update User Profile

**Endpoint:** `PUT /api/users/update_profile/`

**Description:** Update the current user's profile.

**Request:**
```json
{
  "username": "updated_username",
  "profile_pic": "image_file",
  "bio": "Updated bio",
  "current_password": "current_password",  // Required only when changing password
  "new_password": "new_password"  // Optional
}
```

**Response:**
```json
{
  "id": "user_id",
  "username": "updated_username",
  "email": "your_email",
  "profile_pic": "updated_profile_image_url",
  "bio": "Updated bio",
  "last_active": "2023-04-06T12:34:56Z"
}
```

### Update User Location

**Endpoint:** `POST /api/users/update_location/`

**Description:** Update the current user's location.

**Request:**
```json
{
  "latitude": 40.7128,
  "longitude": -74.0060
}
```

**Response:**
```json
{
  "success": true,
  "message": "Location updated successfully",
  "location": {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "updated_at": "2023-04-06T12:34:56Z"
  }
}
```

### Update FCM Token

**Endpoint:** `POST /api/users/update_fcm_token/`

**Description:** Update the FCM token for push notifications.

**Request:**
```json
{
  "fcm_token": "your_fcm_token"
}
```

**Response:**
```json
{
  "success": true,
  "message": "FCM token updated successfully"
}
```

## Pins

### List Pins

**Endpoint:** `GET /api/pins/`

**Description:** Get a list of all public pins and user's own private pins.

**Response:**
```json
[
  {
    "id": "pin_id",
    "owner": {
      "id": "user_id",
      "username": "username"
    },
    "location": {
      "type": "Point",
      "coordinates": [longitude, latitude]
    },
    "title": "Pin Title",
    "description": "Pin Description",
    "track_title": "Song Title",
    "track_artist": "Artist Name",
    "album": "Album Name",
    "track_url": "https://music-service.com/track",
    "service": "spotify",
    "rarity": "common",
    "created_at": "2023-04-06T12:34:56Z",
    "updated_at": "2023-04-06T12:34:56Z",
    "interaction_count": {
      "view": 10,
      "like": 5,
      "collect": 2,
      "share": 1
    }
  }
]
```

### Get Pin

**Endpoint:** `GET /api/pins/{pin_id}/`

**Description:** Get a specific pin's details.

**Response:**
```json
{
  "id": "pin_id",
  "owner": {
    "id": "user_id",
    "username": "username"
  },
  "location": {
    "type": "Point",
    "coordinates": [longitude, latitude]
  },
  "title": "Pin Title",
  "description": "Pin Description",
  "track_title": "Song Title",
  "track_artist": "Artist Name",
  "album": "Album Name",
  "track_url": "https://music-service.com/track",
  "service": "spotify",
  "rarity": "common",
  "created_at": "2023-04-06T12:34:56Z",
  "updated_at": "2023-04-06T12:34:56Z",
  "interaction_count": {
    "view": 10,
    "like": 5,
    "collect": 2,
    "share": 1
  }
}
```

### Create Pin

**Endpoint:** `POST /api/pins/`

**Description:** Create a new pin.

**Request:**
```json
{
  "location": {
    "type": "Point",
    "coordinates": [longitude, latitude]
  },
  "title": "New Pin Title",
  "description": "New Pin Description",
  "track_title": "Song Title",
  "track_artist": "Artist Name",
  "album": "Album Name",
  "track_url": "https://music-service.com/track",
  "service": "spotify",
  "skin": "skin_id",
  "rarity": "common",
  "aura_radius": 100,
  "is_private": false,
  "expiration_date": "2023-05-06T12:34:56Z"
}
```

**Response:**
```json
{
  "id": "new_pin_id",
  "owner": {
    "id": "user_id",
    "username": "username"
  },
  "location": {
    "type": "Point",
    "coordinates": [longitude, latitude]
  },
  "title": "New Pin Title",
  "description": "New Pin Description",
  "track_title": "Song Title",
  "track_artist": "Artist Name",
  "album": "Album Name",
  "track_url": "https://music-service.com/track",
  "service": "spotify",
  "skin": "skin_id",
  "skin_details": {
    "id": "skin_id",
    "name": "Skin Name",
    "image": "skin_image_url"
  },
  "rarity": "common",
  "aura_radius": 100,
  "is_private": false,
  "expiration_date": "2023-05-06T12:34:56Z",
  "created_at": "2023-04-06T12:34:56Z",
  "updated_at": "2023-04-06T12:34:56Z",
  "interaction_count": {
    "view": 0,
    "like": 0,
    "collect": 0,
    "share": 0
  }
}
```

### Update Pin

**Endpoint:** `PUT /api/pins/{pin_id}/`

**Description:** Update an existing pin (owner only).

**Request:**
```json
{
  "title": "Updated Pin Title",
  "description": "Updated Pin Description",
  "is_private": true
}
```

**Response:**
```json
{
  "id": "pin_id",
  "owner": {
    "id": "user_id",
    "username": "username"
  },
  "location": {
    "type": "Point",
    "coordinates": [longitude, latitude]
  },
  "title": "Updated Pin Title",
  "description": "Updated Pin Description",
  "is_private": true,
  // ... other pin fields
}
```

### Delete Pin

**Endpoint:** `DELETE /api/pins/{pin_id}/`

**Description:** Delete a pin (owner only).

**Response:**
- `204 No Content` if successful

### Get Nearby Pins

**Endpoint:** `GET /api/pins/nearby/?latitude=40.7128&longitude=-74.0060&radius=1000`

**Description:** Get pins near a specific location.

**Query Parameters:**
- `latitude`: Latitude coordinate (required)
- `longitude`: Longitude coordinate (required)
- `radius`: Search radius in meters (optional, default: 1000, max: 5000)

**Response:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [longitude, latitude]
      },
      "properties": {
        "id": "pin_id",
        "owner_name": "username",
        "title": "Pin Title",
        "track_title": "Song Title",
        "track_artist": "Artist Name",
        "service": "spotify",
        "rarity": "common",
        "like_count": 5,
        "collect_count": 2,
        "created_at": "2023-04-06T12:34:56Z",
        "distance": 234.5,
        "has_expired": false,
        "aura_radius": 100
      }
    }
  ]
}
```

### Get Trending Pins

**Endpoint:** `GET /api/pins/trending/?days=7&limit=20`

**Description:** Get trending pins based on interaction count.

**Query Parameters:**
- `days`: Number of days to look back (optional, default: 7)
- `limit`: Maximum number of pins to return (optional, default: 20, max: 100)

**Response:**
```json
[
  {
    "id": "pin_id",
    "owner": {
      "id": "user_id",
      "username": "username"
    },
    "location": {
      "type": "Point",
      "coordinates": [longitude, latitude]
    },
    "title": "Pin Title",
    "description": "Pin Description",
    "track_title": "Song Title",
    "track_artist": "Artist Name",
    "album": "Album Name",
    "track_url": "https://music-service.com/track",
    "service": "spotify",
    "rarity": "common",
    "created_at": "2023-04-06T12:34:56Z",
    "updated_at": "2023-04-06T12:34:56Z",
    "interaction_count": {
      "view": 10,
      "like": 5,
      "collect": 2,
      "share": 1
    }
  }
]
```

### Get Map Pins

**Endpoint:** `GET /api/pins/list_map/?latitude=40.7128&longitude=-74.0060&radius=1000`

**Description:** Get pins optimized for map display.

**Query Parameters:**
- `latitude`: Latitude coordinate (optional)
- `longitude`: Longitude coordinate (optional)
- `radius`: Search radius in meters (optional, default: 1000, max: 5000)

**Response:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [longitude, latitude]
      },
      "properties": {
        "id": "pin_id",
        "owner_name": "username",
        "title": "Pin Title",
        "track_title": "Song Title",
        "track_artist": "Artist Name",
        "service": "spotify",
        "rarity": "common",
        "like_count": 5,
        "collect_count": 2,
        "created_at": "2023-04-06T12:34:56Z",
        "distance": 234.5,
        "has_expired": false,
        "aura_radius": 100
      }
    }
  ]
}
```

### Record Pin Interaction

**Endpoints:**
- View: `POST /api/pins/{pin_id}/view/`
- Like: `POST /api/pins/{pin_id}/like/`
- Collect: `POST /api/pins/{pin_id}/collect/`
- Share: `POST /api/pins/{pin_id}/share/`

**Description:** Record various types of interactions with pins.

**Response:**
```json
{
  "success": true,
  "message": "Pin [interaction_type] recorded successfully"
}
```

## Pin Interactions

### List User's Pin Interactions

**Endpoint:** `GET /api/pins/interactions/?type=like`

**Description:** Get a list of the current user's pin interactions.

**Query Parameters:**
- `type`: Filter by interaction type (optional, one of: view, like, collect, share)

**Response:**
```json
[
  {
    "id": "interaction_id",
    "user": "user_id",
    "pin": "pin_id",
    "interaction_type": "like",
    "created_at": "2023-04-06T12:34:56Z"
  }
]
```

### Create Pin Interaction

**Endpoint:** `POST /api/pins/interactions/`

**Description:** Create a new pin interaction.

**Request:**
```json
{
  "pin": "pin_id",
  "interaction_type": "like"
}
```

**Response:**
```json
{
  "id": "interaction_id",
  "user": "user_id",
  "pin": "pin_id",
  "interaction_type": "like",
  "created_at": "2023-04-06T12:34:56Z"
}
```

## Friends

The Friends API endpoints will be implemented in a future update.

## Music Integration

The Music Integration API endpoints will be implemented in a future update.

## Gamification

The Gamification API endpoints will be implemented in a future update.

## Geo Services

The Geo Services API endpoints will be implemented in a future update.

---

## Error Responses

All API endpoints return consistent error responses in the following format:

```json
{
  "error": "ErrorType",
  "detail": "Error message or details"
}
```

Common HTTP error codes:
- `400 Bad Request`: Invalid input
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Permission denied
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

## Rate Limiting

API endpoints have rate limiting to prevent abuse. Headers will include:
- `X-RateLimit-Limit`: Number of requests allowed in the period
- `X-RateLimit-Remaining`: Number of requests remaining in the period
- `X-RateLimit-Reset`: Time when the limit resets, in UTC epoch seconds

When rate limited, you'll receive a `429 Too Many Requests` response. 