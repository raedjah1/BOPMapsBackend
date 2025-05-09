# BOPMaps Backend Caching Implementation

This document outlines the comprehensive caching system implemented for the BOPMaps backend to enhance the existing frontend map caching infrastructure.

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Cache Layers](#cache-layers)
4. [Key Components](#key-components)
5. [API Endpoints](#api-endpoints)
6. [Cache Invalidation](#cache-invalidation)
7. [Usage Examples](#usage-examples)
8. [Performance Monitoring](#performance-monitoring)
9. [Integration with Frontend](#integration-with-frontend)
10. [Deployment Considerations](#deployment-considerations)

## Overview

The BOPMaps backend caching system is designed to provide efficient, scalable caching for map data, focusing particularly on:

- OSM tile proxying and caching
- Vector data delivery (buildings, roads, parks)
- Spatial data query optimization
- Offline region bundling
- User settings synchronization

This system complements the existing frontend caching mechanisms, creating a complete end-to-end solution that significantly improves performance and reduces external API dependencies.

## System Architecture

![Cache Architecture](media/cache_architecture.png)

The caching system operates in multiple layers:

1. **Frontend Cache**: Client-side caching in the Flutter app
2. **CDN/Edge**: For tile and static asset delivery (production only)
3. **Redis Cache**: Primary server-side cache for all data types
4. **Database**: Persistent storage with spatial indexing
5. **OSM/External APIs**: Original data sources, accessed only when needed

## Cache Layers

### 1. Redis Cache

Multiple Redis caches with different expiration times:

- **Default Cache**: General purpose, 7-day expiration
- **Tiles Cache**: Map tiles, 30-day expiration
- **Sessions Cache**: User sessions, 1-day expiration

```python
# Cache configuration in settings.py
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://localhost:6379/1',
        # Configurations and options...
        'TIMEOUT': 60 * 60 * 24 * 7,  # 7 days
    },
    'tiles': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://localhost:6379/2',
        # Configurations and options...
        'TIMEOUT': 60 * 60 * 24 * 30,  # 30 days
    },
    'sessions': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://localhost:6379/3',
        # Configurations and options...
        'TIMEOUT': 60 * 60 * 24,  # 1 day
    }
}
```

### 2. Spatial Caching

Grid-based spatial caching system for geographic data:

- Grid cells divide the world into manageable regions
- Cache keys incorporate geospatial coordinates
- Clustering based on zoom levels
- Precision varies by zoom level

```python
# Spatial cache key example
cache_key = SpatialCache.get_cache_key(
    prefix="buildings",
    lat=40.7128,
    lng=-74.0060,
    zoom=16,
    precision=2  # 0.01 degree precision (~1.1km at equator)
)
```

### 3. HTTP Caching

HTTP-level caching for client and CDN optimization:

- ETags for conditional requests
- Cache-Control headers with appropriate max-age values
- Conditional GET support
- Compression for vector data

## Key Components

### 1. MapCache Class

Core interface for all caching operations:

```python
# Examples of MapCache usage
# Store a tile in cache
MapCache.set_tile(z=16, x=19293, y=24641, data=tile_data)

# Get vector data from cache
buildings = MapCache.get_vector_data(
    data_type='buildings',
    lat=40.7128,
    lng=-74.0060,
    zoom=16,
    radius=1000
)
```

### 2. SpatialCache Class

Specialized spatial caching utilities:

```python
# Get grid cell for a location
lat_grid, lng_grid = SpatialCache.get_grid_cell(40.7128, -74.0060, precision=2)

# Invalidate cache for an area
SpatialCache.invalidate_area(
    prefix="buildings",
    bounds=my_polygon,
    precision=2
)
```

### 3. Middleware

Optimization middleware for request/response handling:

- `MapTileOptimizationMiddleware`: For tile caching and rate limiting
- `VectorDataOptimizationMiddleware`: For vector data ETag handling and compression

### 4. Region Bundling

System for packaging offline data:

```python
# Create a region bundle
task = create_region_bundle.delay(
    north=40.7828,
    south=40.6428,
    east=-73.9060,
    west=-74.1060,
    min_zoom=10,
    max_zoom=18,
    name="New York City"
)
```

## API Endpoints

### Tile Proxy

```
GET /api/geo/tiles/osm/{z}/{x}/{y}.png
```

Proxy service for OpenStreetMap tiles with caching.

### Vector Data

```
GET /api/geo/buildings/?north=40.7828&south=40.6428&east=-73.9060&west=-74.1060&zoom=16
GET /api/geo/roads/?north=40.7828&south=40.6428&east=-73.9060&west=-74.1060&zoom=16
GET /api/geo/parks/?north=40.7828&south=40.6428&east=-73.9060&west=-74.1060&zoom=16
```

Vector data APIs with spatial caching and ETag support.

### Region Bundles

```
POST /api/geo/regions/bundle/
{
  "north": 40.7828,
  "south": 40.6428,
  "east": -73.9060,
  "west": -74.1060,
  "min_zoom": 10,
  "max_zoom": 18,
  "name": "New York City"
}

GET /api/geo/regions/bundle/{task_id}/
GET /api/geo/regions/bundle/{region_id}/download/
```

APIs for creating, monitoring, and downloading offline region bundles.

### User Map Settings

```
GET /api/geo/settings/current/
PUT /api/geo/settings/
{
  "show_feature_info": true,
  "use_3d_buildings": true,
  "default_latitude": 40.7128,
  "default_longitude": -74.0060,
  "default_zoom": 15.0,
  "max_cache_size_mb": 500,
  "theme": "dark"
}
```

APIs for synchronizing user map settings between devices.

## Cache Invalidation

### Time-Based Invalidation

All caches have appropriate TTLs (Time To Live):

- Tiles: 30 days
- Vector data: 1 day
- User settings: 30 days
- Trending areas: 30 minutes

### Event-Based Invalidation

Cache entries are invalidated on relevant data changes:

```python
# Invalidate pins near a location when a new pin is created
MapCache.invalidate_pins_near(lat=40.7128, lng=-74.0060, radius=1000)

# Invalidate user settings when updated
MapCache.invalidate_user_settings(user_id=123)
```

### Spatial Invalidation

Grid-based spatial invalidation for geographic regions:

```python
# Invalidate all caches in a region
count = SpatialCache.invalidate_area("buildings", bounds_polygon)
```

## Usage Examples

### Caching Tiles

```python
# In OSMTileView.get
def get(self, request, z, x, y, format=None):
    # Check cache first
    cached_tile = MapCache.get_tile(z, x, y)
    if cached_tile:
        return HttpResponse(cached_tile, content_type="image/png")
    
    # If not in cache, fetch from OSM
    osm_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    response = requests.get(osm_url, stream=True, timeout=5)
    
    if response.status_code == 200:
        # Store in cache
        MapCache.set_tile(z, x, y, response.content)
        return HttpResponse(response.content, content_type="image/png")
```

### Caching Vector Data

```python
# In BuildingViewSet.list
def list(self, request, *args, **kwargs):
    # Calculate cache key parameters
    lat = (float(request.query_params.get('north', 0)) + 
          float(request.query_params.get('south', 0))) / 2
    lng = (float(request.query_params.get('east', 0)) + 
          float(request.query_params.get('west', 0))) / 2
    zoom = int(request.query_params.get('zoom', 16))
    
    # Try to get from cache
    cached_data = MapCache.get_vector_data(
        data_type='buildings',
        lat=lat,
        lng=lng,
        zoom=zoom,
        additional_params={...}
    )
    
    if cached_data:
        return Response(cached_data)
        
    # If not in cache, fetch and store
    queryset = self.get_queryset()
    serializer = self.get_serializer(queryset, many=True)
    data = serializer.data
    
    MapCache.set_vector_data(
        data_type='buildings',
        lat=lat,
        lng=lng,
        zoom=zoom,
        data=data,
        additional_params={...}
    )
    
    return Response(data)
```

## Performance Monitoring

The caching system includes monitoring capabilities:

### Cache Statistics

```python
# Get cache statistics
stats = MapCache.get_cache_stats()
```

This returns:

```json
{
  "redis_version": "6.2.6",
  "used_memory_human": "1.2G",
  "hit_rate": 0.87,
  "total_keys": 158342,
  "tile_keys": 124536,
  "vector_keys": 29874,
  "pins_keys": 3248,
  "settings_keys": 684
}
```

### Logging

Comprehensive logging for cache operations:

```python
# Example log output
INFO [2023-08-15 14:32:18] bopmaps.cache: Cache hit for buildings:grid:40.71:74.00:zoom:16
WARNING [2023-08-15 14:35:42] bopmaps.cache: Cache miss for high-traffic area at 40.71,-74.00
```

## Integration with Frontend

### Flutter Integration

The Flutter app's `MapCacheManager` class should be updated to use the new backend APIs:

```dart
// lib/services/map_cache_manager.dart

Future<Uint8List?> getTileFromBackend(TileCoordinates coords) async {
  try {
    final url = '${AppConstants.apiBaseUrl}/api/geo/tiles/osm/${coords.z}/${coords.x}/${coords.y}.png';
    
    final response = await http.get(Uri.parse(url));
    
    if (response.statusCode == 200) {
      return response.bodyBytes;
    }
    return null;
  } catch (e) {
    debugPrint('Error fetching tile from backend: $e');
    return null;
  }
}
```

### Settings Synchronization

The frontend `MapSettingsProvider` should synchronize with the backend:

```dart
// In MapSettingsProvider.loadSettings
Future<void> loadSettings() async {
  try {
    final response = await http.get(
      Uri.parse('${AppConstants.apiBaseUrl}/api/geo/settings/current/'),
      headers: {'Authorization': 'Bearer $userToken'},
    );
    
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      _showFeatureInfo = data['show_feature_info'];
      _use3DBuildings = data['use_3d_buildings'];
      _defaultLatitude = data['default_latitude'];
      _defaultLongitude = data['default_longitude'];
      _defaultZoom = data['default_zoom'];
      _maxCacheSizeMb = data['max_cache_size_mb'];
      _theme = data['theme'];
      
      notifyListeners();
    }
  } catch (e) {
    debugPrint('Error loading settings: $e');
  }
}
```

## Deployment Considerations

### Redis Configuration

For production, configure Redis with:

- Persistence (RDB snapshots and AOF logs)
- Memory limits to prevent OOM issues
- Appropriate eviction policies

```
maxmemory 2gb
maxmemory-policy allkeys-lru
```

### CDN Integration

For production, use a CDN for tile delivery:

- Configure correct cache headers for CDN
- Consider using a pull-through CDN model
- Implement cache purging for invalidation

### Monitoring

Monitor cache performance with:

- Redis monitoring tools (RedisInsight, Prometheus exporters)
- Application logs with cache hit/miss tracking
- Alert on low hit rates or high miss rates

### Scaling

The system can scale horizontally by:

- Adding more Redis instances with sharding
- Deploying multiple Django instances behind a load balancer
- Using Redis Cluster for distributing cached data 