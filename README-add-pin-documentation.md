# BOPMaps Pin API Documentation

This document provides comprehensive documentation for the pin-related endpoints in the BOPMaps backend API.

## Base URL

All pin-related endpoints are prefixed with: `/api/pins/`

## Authentication

All endpoints require authentication. Include the JWT token in the Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

## Pin Endpoints

### 1. Create a Pin
- **Endpoint**: `POST /api/pins/`
- **Description**: Create a new music pin at a location
- **Request Body**:
```json
{
    "location": {
        "type": "Point",
        "coordinates": [longitude, latitude]
    },
    "title": "string",
    "description": "string (optional)",
    "track_title": "string",
    "track_artist": "string",
    "album": "string (optional)",
    "track_url": "string (must be valid music service URL)",
    "service": "spotify|apple|soundcloud",
    "skin": "integer (pin skin ID)",
    "rarity": "common|uncommon|rare|epic|legendary",
    "aura_radius": "integer (10-1000 meters)",
    "is_private": "boolean",
    "expiration_date": "datetime (optional)"
}
```

### 2. Get Pins for Map Display
- **Endpoint**: `GET /api/pins/list_map/`
- **Description**: Get pins optimized for map display with clustering
- **Query Parameters**:
  - `latitude`: float (required)
  - `longitude`: float (required)
  - `radius`: integer (meters, default: 1000, max: 10000)
  - `zoom`: integer (map zoom level, default: 13)
- **Response Format**:
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
                "id": "integer",
                "owner_name": "string",
                "title": "string",
                "track_title": "string",
                "track_artist": "string",
                "service": "string",
                "rarity": "string",
                "like_count": "integer",
                "collect_count": "integer",
                "created_at": "datetime",
                "distance": "float (meters)",
                "has_expired": "boolean",
                "aura_radius": "integer"
            }
        }
    ],
    "cluster_params": {
        "enabled": "boolean",
        "distance": "integer",
        "max_cluster_radius": "integer"
    }
}
```

### 3. Get Nearby Pins
- **Endpoint**: `GET /api/pins/nearby/`
- **Description**: Get pins near a specific location
- **Query Parameters**:
  - `latitude`: float (required)
  - `longitude`: float (required)
  - `radius`: integer (meters, default: 1000, max: 5000)

### 4. Get Trending Pins
- **Endpoint**: `GET /api/pins/trending/`
- **Description**: Get trending pins based on interaction count
- **Query Parameters**:
  - `days`: integer (time window in days, default: 7)
  - `limit`: integer (max results, default: 20, max: 100)

### 5. Pin Details
- **Endpoint**: `GET /api/pins/{pin_id}/`
- **Description**: Get detailed information about a specific pin
- **Response Format**:
```json
{
    "id": "integer",
    "owner": {
        "id": "integer",
        "username": "string",
        "profile_image": "url"
    },
    "location": {
        "type": "Point",
        "coordinates": [longitude, latitude]
    },
    "title": "string",
    "description": "string",
    "track_title": "string",
    "track_artist": "string",
    "album": "string",
    "track_url": "string",
    "service": "string",
    "skin": "integer",
    "skin_details": {
        "id": "integer",
        "name": "string",
        "image_url": "string"
    },
    "rarity": "string",
    "aura_radius": "integer",
    "is_private": "boolean",
    "expiration_date": "datetime",
    "created_at": "datetime",
    "updated_at": "datetime",
    "interaction_count": {
        "view": "integer",
        "like": "integer",
        "collect": "integer",
        "share": "integer"
    },
    "distance": "float (meters, if available)",
    "has_expired": "boolean"
}
```

### 6. Pin Map Details
- **Endpoint**: `GET /api/pins/{pin_id}/map_details/`
- **Description**: Get detailed pin information for map display with aura visualization settings
- **Response Format**:
```json
{
    // ... all fields from Pin Details endpoint ...
    "visualization": {
        "aura_color": "string (hex color)",
        "aura_opacity": "float (0.6-0.9)",
        "pulse_animation": "boolean",
        "icon_url": "string (url)"
    }
}
```

### 7. Get Recommended Pins
- **Endpoint**: `GET /api/pins/recommended/`
- **Description**: Get personalized pin recommendations based on user preferences and location
- **Query Parameters**:
  - `latitude`: float (optional)
  - `longitude`: float (optional)
  - `limit`: integer (default: 20, max: 50)
- **Response**: List of pins personalized to the user's preferences

### 8. Advanced Search
- **Endpoint**: `GET /api/pins/advanced_search/`
- **Description**: Search pins with multiple criteria and filtering options
- **Query Parameters**:
  - `service`: string (spotify|apple|soundcloud)
  - `genre`: string
  - `mood`: string
  - `artist`: string (partial match)
  - `track`: string (partial match)
  - `rarity`: string (common|uncommon|rare|epic|legendary)
  - `time_range`: string (today|week|month)
  - `min_likes`: integer
  - `sort_by`: string (created_at|likes|collects|views)
  - `limit`: integer (default: 20, max: 50)
  - `offset`: integer (default: 0)
- **Response Format**:
```json
{
    "count": "integer",
    "next": "integer or null",
    "previous": "integer or null",
    "results": [
        {
            // Pin object, same as Pin Details endpoint
        }
    ]
}
```

### 9. Similar Pins
- **Endpoint**: `GET /api/pins/{pin_id}/similar/`
- **Description**: Find pins similar to a specific pin based on attributes
- **Response**: List of similar pins

### 10. Pin Analytics
- **Endpoint**: `GET /api/pins/{pin_id}/analytics/`
- **Description**: Get detailed analytics for a pin (only available to pin owner)
- **Response Format**:
```json
{
    "id": "integer",
    "pin": "integer",
    "pin_title": "string",
    "total_views": "integer",
    "unique_viewers": "integer",
    "collection_rate": "float",
    "peak_hour": "integer (0-23)",
    "peak_hour_formatted": "string (12-hour format)",
    "engagement_rate": "float (percentage)",
    "hourly_distribution": {
        "0": "integer",
        "1": "integer",
        // ... counts for each hour 0-23
    },
    "last_updated": "datetime"
}
```

### 11. Batch Interactions
- **Endpoint**: `POST /api/pins/batch_interact/`
- **Description**: Process multiple pin interactions in a single request
- **Request Body**:
```json
{
    "interactions": [
        {
            "pin_id": "integer",
            "type": "view|collect|like|share"
        },
        // ... more interactions
    ]
}
```
- **Response Format**:
```json
[
    {
        "pin_id": "integer",
        "status": "success|error",
        "message": "string (only on error)"
    },
    // ... results for each interaction
]
```

### 12. WebSocket Connection Info
- **Endpoint**: `GET /api/pins/websocket_connect/`
- **Description**: Get WebSocket connection information for real-time pin updates
- **Response Format**:
```json
{
    "websocket_url": "string (WebSocket URL)",
    "supported_events": ["string", "string"]
}
```

## Pin Interactions

### 1. View a Pin
- **Endpoint**: `POST /api/pins/{pin_id}/view/`
- **Description**: Record a view interaction with a pin

### 2. Like a Pin
- **Endpoint**: `POST /api/pins/{pin_id}/like/`
- **Description**: Record a like interaction with a pin

### 3. Collect a Pin
- **Endpoint**: `POST /api/pins/{pin_id}/collect/`
- **Description**: Record a collect interaction with a pin

### 4. Share a Pin
- **Endpoint**: `POST /api/pins/{pin_id}/share/`
- **Description**: Record a share interaction with a pin

### 5. List User's Pin Interactions
- **Endpoint**: `GET /api/pins/interactions/`
- **Description**: Get list of user's pin interactions
- **Query Parameters**:
  - `type`: string (filter by interaction type: view|collect|like|share)
- **Response Format**:
```json
[
    {
        "id": "integer",
        "user": "integer",
        "pin": "integer",
        "interaction_type": "string",
        "created_at": "datetime"
    }
]
```

**Note**: Pin interactions are unique per user, pin, and interaction type combination. Attempting to create a duplicate interaction will update the timestamp of the existing interaction.

## Music Track Selection

When creating pins, you can use these endpoints to select music tracks:

### 1. Search Tracks
- **Endpoint**: `GET /api/music/tracks/search/`
- **Query Parameters**:
  - `q`: string (search query, required)
  - `service`: string (spotify|apple|soundcloud)
  - `limit`: integer (default: 10)

### 2. Recently Played Tracks
- **Endpoint**: `GET /api/music/tracks/recently_played/`
- **Query Parameters**:
  - `service`: string (spotify|apple|soundcloud)
  - `limit`: integer (default: 10)

### 3. Saved/Liked Tracks
- **Endpoint**: `GET /api/music/tracks/saved_tracks/`
- **Query Parameters**:
  - `service`: string (spotify|apple|soundcloud)
  - `limit`: integer (default: 50)
  - `offset`: integer (default: 0)

### 4. User's Playlists
- **Endpoint**: `GET /api/music/tracks/playlists/`
- **Query Parameters**:
  - `service`: string (spotify|apple|soundcloud)
  - `limit`: integer (default: 20)

## Pin Model Details

### Pin Properties
- `id`: Unique identifier
- `owner`: User who created the pin
- `location`: Geographic point (longitude, latitude)
- `title`: Pin title
- `description`: Optional description
- `track_title`: Music track title
- `track_artist`: Artist name
- `album`: Optional album name
- `track_url`: URL to the track on the music service
- `service`: Music service (spotify|apple|soundcloud)
- `skin`: Reference to pin skin customization
- `rarity`: Pin rarity level
- `aura_radius`: Discovery radius in meters (10-1000)
- `is_private`: Whether the pin is private
- `expiration_date`: Optional expiration datetime
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

### Pin Interaction Types
- `view`: User viewed the pin
- `collect`: User collected the pin
- `like`: User liked the pin
- `share`: User shared the pin

## Example Usage with Flutter

### Creating a Pin
```dart
final response = await dio.post(
  '/api/pins/',
  data: {
    'location': {
      'type': 'Point',
      'coordinates': [longitude, latitude]
    },
    'title': 'My Awesome Song',
    'track_title': 'Song Name',
    'track_artist': 'Artist Name',
    'track_url': 'https://open.spotify.com/track/...',
    'service': 'spotify',
    'aura_radius': 50,
    'is_private': false
  }
);
```

### Getting Nearby Pins
```dart
final response = await dio.get(
  '/api/pins/nearby/',
  queryParameters: {
    'latitude': userLocation.latitude,
    'longitude': userLocation.longitude,
    'radius': 1000
  }
);
```

### Interacting with a Pin
```dart
// Like a pin
await dio.post('/api/pins/$pinId/like/');

// Collect a pin
await dio.post('/api/pins/$pinId/collect/');
```

## Error Handling

The API returns standard HTTP status codes:
- 200: Success
- 400: Bad Request (invalid parameters)
- 401: Unauthorized (invalid/missing token)
- 403: Forbidden (insufficient permissions)
- 404: Not Found
- 500: Server Error

Error responses include a message:
```json
{
    "error": "Error message description"
}
```

## Additional Notes

### Service Colors
Each music service has a designated color for map visualization:
- Spotify: #1DB954
- Apple Music: #FC3C44
- SoundCloud: #FF7700

### Rarity Levels and Aura Opacity
Pin rarity affects the opacity of the aura on the map:
- Common: 0.6
- Uncommon: 0.7
- Rare: 0.8
- Epic: 0.85
- Legendary: 0.9

### Map Clustering
Clustering behavior adjusts based on zoom level:
- Zoom < 12: Large clusters (radius up to 5000m)
- Zoom 12-14: Medium clusters (radius up to 2000m)
- Zoom 15+: Small clusters (radius up to 1000m)
- Zoom 16+: No clustering

### Rate Limits and Caching
- View interactions are rate-limited to one per hour per pin
- Map data is cached for 5 minutes
- Trending calculations are cached for 15 minutes

## Real-time Updates via WebSockets

BOPMaps provides real-time pin updates through WebSockets for a more interactive experience.

### Connection

Connect to the WebSocket endpoint:
```
ws://your-server-url/ws/pins/
```

Authentication is required using the same JWT token used for API requests.

### Events

The WebSocket connection supports the following events:

#### Client to Server:
- `heartbeat`: Keep the connection alive
- `subscribe_pin`: Subscribe to updates for a specific pin

#### Server to Client:
- `connection_established`: Sent when the connection is successfully established
- `new_pin`: Sent when a new pin is created in your vicinity
- `pin_update`: Sent when a pin you're subscribed to is updated
- `trending_update`: Sent when the trending pins list is updated

### Example Usage with Flutter

```dart
// Connect to WebSocket
final wsUrl = Uri.parse('ws://your-server-url/ws/pins/');
final ws = WebSocket(
  wsUrl.toString(),
  headers: {'Authorization': 'Bearer $token'}
);

// Handle incoming messages
ws.stream.listen((message) {
  final data = jsonDecode(message);
  switch (data['type']) {
    case 'connection_established':
      print('Connected to pin updates');
      break;
    case 'new_pin':
      print('New pin created: ${data['title']}');
      // Update map with the new pin
      break;
  }
});

// Subscribe to a specific pin updates
ws.send(jsonEncode({
  'type': 'subscribe_pin',
  'pin_id': 123
}));
```

## Additional Features

### Enhanced Discovery

Pins now include additional fields to improve discovery and relevance:

- `genre`: Music genre categorization
- `mood`: Emotional context of the music
- `tags`: Array of custom tags for better organization

These fields can be set when creating pins and used for filtering and recommendations. 