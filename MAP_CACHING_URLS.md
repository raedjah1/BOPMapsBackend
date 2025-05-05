# BOPMaps Map Caching API Endpoints

This document provides a comprehensive list of all map caching-related API endpoints and their usage for frontend integration.

## Base URL

```
https://your-api-domain.com/api/v1
```

Replace `your-api-domain.com` with your actual API domain.

## Authentication

All endpoints require JWT authentication. Include the token in the Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

## Map Tile Endpoints

### 1. Cached Tile Retrieval
```
GET /tiles/{z}/{x}/{y}.png
```
- Parameters:
  - `z`: Zoom level (0-19)
  - `x`: X coordinate
  - `y`: Y coordinate
- Response: PNG image
- Headers:
  - `Cache-Control: max-age=2592000` (30 days)
  - `ETag`: Unique tile identifier

Example:
```javascript
const getTile = async (z, x, y) => {
  const response = await fetch(`/api/v1/tiles/${z}/${x}/${y}.png`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.blob();
};
```

## Vector Data Endpoints

### 1. Buildings Data
```
GET /geo/buildings/
```
- Query Parameters:
  - `bounds`: Bounding box (format: `minLat,minLng,maxLat,maxLng`)
  - `zoom`: Current zoom level
- Response: GeoJSON

Example:
```javascript
const getBuildings = async (bounds, zoom) => {
  const response = await fetch(`/api/v1/geo/buildings/?bounds=${bounds}&zoom=${zoom}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};
```

### 2. Roads Data
```
GET /geo/roads/
```
- Query Parameters:
  - `bounds`: Bounding box
  - `zoom`: Current zoom level
- Response: GeoJSON

## Region Bundle Endpoints

### 1. List Available Regions
```
GET /geo/regions/
```
- Query Parameters:
  - `bounds`: Optional bounding box to filter regions
- Response: List of available cached regions

### 2. Create Region Bundle
```
POST /geo/regions/bundle/
```
- Request Body:
```json
{
  "bounds": {
    "minLat": 40.7,
    "minLng": -74.1,
    "maxLat": 40.8,
    "maxLng": -74.0
  },
  "zoom_levels": [14, 15, 16],
  "include_vector_data": true
}
```
- Response:
```json
{
  "task_id": "abc123",
  "status": "pending"
}
```

### 3. Check Bundle Status
```
GET /geo/regions/bundle/{task_id}/
```
- Response:
```json
{
  "task_id": "abc123",
  "status": "completed",
  "download_url": "https://..."
}
```

### 4. Download Region Bundle
```
GET /geo/regions/bundle/{task_id}/download/
```
- Response: ZIP file containing cached tiles and vector data

## Cache Management

### 1. Cache Statistics
```
GET /geo/cache/stats/
```
- Response:
```json
{
  "total_size_bytes": 1000000,
  "tile_cache_size_bytes": 500000,
  "vector_cache_size_bytes": 500000,
  "hit_rate": 0.95
}
```

## Implementation Example

Here's a complete example of implementing tile caching in your frontend:

```typescript
class MapCache {
  private baseUrl: string;
  private token: string;

  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl;
    this.token = token;
  }

  async getTile(z: number, x: number, y: number): Promise<Blob> {
    const url = `${this.baseUrl}/tiles/${z}/${x}/${y}.png`;
    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${this.token}`
      }
    });
    
    if (!response.ok) {
      throw new Error(`Failed to fetch tile: ${response.statusText}`);
    }
    
    return response.blob();
  }

  async getRegionBundle(bounds: BoundingBox, zoomLevels: number[]): Promise<string> {
    // Create bundle request
    const response = await fetch(`${this.baseUrl}/geo/regions/bundle/`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        bounds,
        zoom_levels: zoomLevels,
        include_vector_data: true
      })
    });

    const { task_id } = await response.json();
    return task_id;
  }

  async checkBundleStatus(taskId: string): Promise<BundleStatus> {
    const response = await fetch(`${this.baseUrl}/geo/regions/bundle/${taskId}/`, {
      headers: {
        'Authorization': `Bearer ${this.token}`
      }
    });
    
    return response.json();
  }
}

// Usage example
const mapCache = new MapCache('https://api.bopmaps.com/api/v1', 'your_token');

// Fetch a single tile
const tile = await mapCache.getTile(15, 16384, 16384);

// Create an offline region bundle
const taskId = await mapCache.getRegionBundle({
  minLat: 40.7,
  minLng: -74.1,
  maxLat: 40.8,
  maxLng: -74.0
}, [14, 15, 16]);

// Check bundle status
const status = await mapCache.checkBundleStatus(taskId);
```

## Error Handling

All endpoints follow standard HTTP status codes:

- 200: Success
- 304: Not Modified (when using ETags)
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 429: Too Many Requests
- 500: Internal Server Error

Example error response:
```json
{
  "error": "Invalid bounds format",
  "detail": "Bounds must be in format: minLat,minLng,maxLat,maxLng",
  "code": "INVALID_BOUNDS"
}
```

## Rate Limiting

- Tile requests: 100 requests per minute per user
- Vector data requests: 50 requests per minute per user
- Region bundle creation: 5 requests per hour per user

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1623456789
```

## Best Practices

1. **Implement Client-Side Caching**
   - Use browser's Cache API or IndexedDB for offline storage
   - Respect Cache-Control headers
   - Store ETags for conditional requests

2. **Optimize Requests**
   - Bundle nearby tile requests
   - Use appropriate zoom levels
   - Implement request debouncing for vector data

3. **Handle Offline Mode**
   - Download region bundles for offline use
   - Implement fallback mechanisms
   - Show appropriate UI indicators

4. **Monitor Usage**
   - Track cache hit rates
   - Monitor rate limit usage
   - Log errors and failed requests

## WebSocket Events

Subscribe to cache-related events:
```
ws://your-api-domain.com/ws/cache/
```

Events:
- `cache.purged`: When cache is cleared
- `bundle.completed`: When region bundle is ready
- `storage.warning`: When cache size approaches limits 