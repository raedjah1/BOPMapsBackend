# BOPMaps Backend Integration Guide

This guide explains how to connect the BOPMaps backend caching system with your existing Flutter frontend caching implementation.

## Overview

The backend caching system is designed to complement, not replace, your existing frontend caching. The integration creates a hybrid approach that:

1. Leverages server-side caching for better performance
2. Reduces OSM API rate limiting issues  
3. Maintains offline capabilities
4. Provides cross-device settings synchronization
5. Preserves your 2.5D rendering engine and UX

## Architecture Integration

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Frontend     │    │     Backend     │    │  External APIs  │
│  Cache System   │◄───►   Cache System  │◄───►   (OSM, etc.)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │
        │                       │
        ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│  Local Storage  │    │   Redis Cache   │
│   (Map Data)    │    │ (Shared Cache)  │
└─────────────────┘    └─────────────────┘
```

## Integration Steps

### 1. Configure Backend Connection

#### Add API Base URL to your Frontend

In your `lib/config/constants.dart` (or equivalent):

```dart
class AppConstants {
  // Existing constants...
  
  // Backend API URL - update for different environments
  static const String apiBaseUrl = 'https://api.bopmaps.com'; // Production
  // static const String apiBaseUrl = 'http://localhost:8000'; // Development
  
  // API timeout in seconds
  static const int apiTimeoutSeconds = 15;
}
```

#### Add Authentication Helper (if using auth)

In `lib/services/auth_service.dart` (or create it):

```dart
import 'package:shared_preferences/shared_preferences.dart';

class AuthService {
  static const String _tokenKey = 'auth_token';
  
  // Get stored token
  Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }
  
  // Get Authorization header
  Future<Map<String, String>> getAuthHeaders() async {
    final token = await getToken();
    if (token != null) {
      return {'Authorization': 'Bearer $token'};
    }
    return {};
  }
}
```

### 2. Update MapCacheManager for Tile Proxying

Modify your existing `MapCacheManager` to query the backend before directly accessing OSM:

```dart
import 'package:http/http.dart' as http;
import '../config/constants.dart';
import '../services/auth_service.dart';

class MapCacheManager {
  // Your existing code...
  final AuthService _authService = AuthService();
  
  // Add this method to check backend cache first
  Future<Uint8List?> getTileFromBackend(int z, int x, int y) async {
    try {
      final headers = await _authService.getAuthHeaders();
      headers['Accept'] = 'image/png';
      
      final url = '${AppConstants.apiBaseUrl}/api/geo/tiles/osm/$z/$x/$y.png';
      final response = await http.get(
        Uri.parse(url),
        headers: headers,
      ).timeout(Duration(seconds: AppConstants.apiTimeoutSeconds));
      
      if (response.statusCode == 200) {
        return response.bodyBytes;
      }
      return null;
    } catch (e) {
      print('Backend tile fetch error: $e');
      return null;
    }
  }
  
  // Modify your existing tile fetching logic
  Future<Uint8List?> getTile(int z, int x, int y) async {
    // First check your local memory cache
    // Then check your local disk cache
    // Then try the backend
    final backendTile = await getTileFromBackend(z, x, y);
    if (backendTile != null) {
      // Store in local cache for offline use
      await _saveTileToCache(z, x, y, backendTile);
      return backendTile;
    }
    
    // Fall back to direct OSM access (your existing code)
    return _getDirectOsmTile(z, x, y);
  }
}
```

### 3. Update Vector Data Services for Building Data

Update or create a service to fetch vector data from the backend:

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/constants.dart';
import '../models/building.dart';
import '../services/auth_service.dart';

class VectorDataService {
  final AuthService _authService = AuthService();
  
  // Fetch buildings from backend
  Future<List<Building>> getBuildings(double north, double south, double east, double west, int zoom) async {
    try {
      final headers = await _authService.getAuthHeaders();
      headers['Accept'] = 'application/json';
      
      final url = Uri.parse('${AppConstants.apiBaseUrl}/api/geo/buildings/').replace(
        queryParameters: {
          'north': north.toString(),
          'south': south.toString(),
          'east': east.toString(),
          'west': west.toString(),
          'zoom': zoom.toString(),
        },
      );
      
      final response = await http.get(
        url,
        headers: headers,
      ).timeout(Duration(seconds: AppConstants.apiTimeoutSeconds));
      
      if (response.statusCode == 200) {
        final Map<String, dynamic> data = json.decode(response.body);
        return (data['results'] as List)
            .map((building) => Building.fromJson(building))
            .toList();
      }
      
      // If backend fails, fall back to your direct Overpass API call
      return _getDirectFromOverpass(north, south, east, west, zoom);
    } catch (e) {
      print('Backend building fetch error: $e');
      return _getDirectFromOverpass(north, south, east, west, zoom);
    }
  }
  
  // Your existing Overpass API implementation
  Future<List<Building>> _getDirectFromOverpass(double north, double south, double east, double west, int zoom) async {
    // Your existing implementation...
    return [];
  }
  
  // Similar methods for roads, parks, etc.
}
```

### 4. Implement Region Bundle Downloading

Create a service for working with region bundles:

```dart
import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import '../config/constants.dart';
import '../models/region.dart';
import '../services/auth_service.dart';

class RegionBundleService {
  final AuthService _authService = AuthService();
  
  // Create a region bundle task
  Future<String?> createRegionBundle(double north, double south, double east, double west, 
                                    int minZoom, int maxZoom) async {
    try {
      final headers = await _authService.getAuthHeaders();
      headers['Content-Type'] = 'application/json';
      headers['Accept'] = 'application/json';
      
      final response = await http.post(
        Uri.parse('${AppConstants.apiBaseUrl}/api/geo/regions/bundle/'),
        headers: headers,
        body: json.encode({
          'north': north,
          'south': south,
          'east': east,
          'west': west,
          'min_zoom': minZoom,
          'max_zoom': maxZoom,
        }),
      );
      
      if (response.statusCode == 200 || response.statusCode == 201) {
        final data = json.decode(response.body);
        return data['task_id'];
      }
      return null;
    } catch (e) {
      print('Error creating region bundle: $e');
      return null;
    }
  }
  
  // Check bundle task status
  Future<Map<String, dynamic>?> checkBundleStatus(String taskId) async {
    try {
      final headers = await _authService.getAuthHeaders();
      headers['Accept'] = 'application/json';
      
      final response = await http.get(
        Uri.parse('${AppConstants.apiBaseUrl}/api/geo/regions/bundle/$taskId/'),
        headers: headers,
      );
      
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
      return null;
    } catch (e) {
      print('Error checking bundle status: $e');
      return null;
    }
  }
  
  // Download the bundle
  Future<File?> downloadBundle(String taskId, void Function(double) onProgress) async {
    try {
      final headers = await _authService.getAuthHeaders();
      
      final response = await http.get(
        Uri.parse('${AppConstants.apiBaseUrl}/api/geo/regions/bundle/$taskId/'),
        headers: headers,
      );
      
      if (response.statusCode == 200) {
        // Save the file
        final directory = await getApplicationDocumentsDirectory();
        final filePath = '${directory.path}/region_bundles/$taskId.zip';
        
        // Create directory if it doesn't exist
        final dir = Directory('${directory.path}/region_bundles');
        if (!await dir.exists()) {
          await dir.create(recursive: true);
        }
        
        // Write file
        final file = File(filePath);
        await file.writeAsBytes(response.bodyBytes);
        return file;
      }
      return null;
    } catch (e) {
      print('Error downloading bundle: $e');
      return null;
    }
  }
  
  // Extract bundle to your cache structure
  Future<bool> extractBundle(File bundleFile, String regionId) async {
    try {
      // Implementation depends on your caching structure
      // This is where you would extract the ZIP file and 
      // integrate it with your existing cache
      // ...
      
      return true;
    } catch (e) {
      print('Error extracting bundle: $e');
      return false;
    }
  }
}
```

### 5. Implement Settings Synchronization

Create a service for syncing map settings:

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/constants.dart';
import '../models/map_settings.dart';
import '../services/auth_service.dart';

class MapSettingsSyncService {
  final AuthService _authService = AuthService();
  
  // Get settings from server
  Future<MapSettings?> getMapSettings() async {
    try {
      final headers = await _authService.getAuthHeaders();
      headers['Accept'] = 'application/json';
      
      final response = await http.get(
        Uri.parse('${AppConstants.apiBaseUrl}/api/geo/settings/map/'),
        headers: headers,
      );
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return MapSettings.fromJson(data);
      }
      return null;
    } catch (e) {
      print('Error fetching map settings: $e');
      return null;
    }
  }
  
  // Save settings to server
  Future<bool> saveMapSettings(MapSettings settings) async {
    try {
      final headers = await _authService.getAuthHeaders();
      headers['Content-Type'] = 'application/json';
      headers['Accept'] = 'application/json';
      
      final response = await http.post(
        Uri.parse('${AppConstants.apiBaseUrl}/api/geo/settings/map/'),
        headers: headers,
        body: json.encode(settings.toJson()),
      );
      
      return response.statusCode == 200 || response.statusCode == 201;
    } catch (e) {
      print('Error saving map settings: $e');
      return false;
    }
  }
}
```

### 6. Update MapSettingsProvider

Modify your `MapSettingsProvider` to sync with the backend:

```dart
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/map_settings_sync_service.dart';
import '../models/map_settings.dart';

class MapSettingsProvider with ChangeNotifier {
  // Your existing code...
  final MapSettingsSyncService _syncService = MapSettingsSyncService();
  DateTime? _lastSyncTime;
  
  // Initialize with sync
  Future<void> initialize() async {
    await _loadLocalSettings();
    await syncWithServer();
  }
  
  // Sync settings with server
  Future<void> syncWithServer() async {
    try {
      final serverSettings = await _syncService.getMapSettings();
      if (serverSettings != null) {
        // Update local settings with server settings
        _use3DBuildings = serverSettings.use3DBuildings;
        _showFeatureInfo = serverSettings.showFeatureInfo;
        _defaultZoom = serverSettings.defaultZoom;
        _maxCacheSizeMb = serverSettings.maxCacheSizeMb;
        
        // Save to local storage
        await _saveLocalSettings();
        
        _lastSyncTime = DateTime.now();
        notifyListeners();
      }
    } catch (e) {
      print('Error syncing settings from server: $e');
    }
  }
  
  // Add sync to your setters
  Future<void> setUse3DBuildings(bool value) async {
    _use3DBuildings = value;
    await _saveLocalSettings();
    
    // Also sync to server
    final settings = MapSettings(
      use3DBuildings: _use3DBuildings,
      showFeatureInfo: _showFeatureInfo,
      defaultZoom: _defaultZoom,
      maxCacheSizeMb: _maxCacheSizeMb,
    );
    
    _syncService.saveMapSettings(settings).then((success) {
      if (success) {
        _lastSyncTime = DateTime.now();
      }
    });
    
    notifyListeners();
  }
  
  // Similar updates to other setters...
}
```

## Testing Your Integration

### 1. Configure Testing Environments

Create a simple way to switch between direct API access and backend-proxied access:

```dart
// lib/config/environment.dart
enum ApiMode {
  direct,    // Direct to OSM/Overpass
  backend,   // Through backend proxy
  hybrid     // Try backend first, fall back to direct
}

class Environment {
  static ApiMode apiMode = ApiMode.hybrid;
  
  static bool shouldUseBackend() {
    return apiMode == ApiMode.backend || apiMode == ApiMode.hybrid;
  }
  
  static bool shouldUseDirectApi() {
    return apiMode == ApiMode.direct || 
          (apiMode == ApiMode.hybrid && _isBackendUnreachable());
  }
  
  static bool _isBackendUnreachable() {
    // Implementation to check if backend is unreachable
    return false;
  }
}
```

### 2. Test Each Integration Point

Create a diagnostic screen to test each integration point:

```dart
import 'package:flutter/material.dart';
import '../services/map_cache_manager.dart';
import '../services/vector_data_service.dart';
import '../services/region_bundle_service.dart';
import '../services/map_settings_sync_service.dart';

class BackendDiagnosticsScreen extends StatefulWidget {
  @override
  _BackendDiagnosticsScreenState createState() => _BackendDiagnosticsScreenState();
}

class _BackendDiagnosticsScreenState extends State<BackendDiagnosticsScreen> {
  final MapCacheManager _cacheManager = MapCacheManager();
  final VectorDataService _vectorDataService = VectorDataService();
  final RegionBundleService _bundleService = RegionBundleService();
  final MapSettingsSyncService _settingsService = MapSettingsSyncService();
  
  bool _tileProxyWorking = false;
  bool _buildingDataWorking = false;
  bool _bundleCreationWorking = false;
  bool _settingsSyncWorking = false;
  
  @override
  void initState() {
    super.initState();
    _runDiagnostics();
  }
  
  Future<void> _runDiagnostics() async {
    // Test tile proxy
    final tile = await _cacheManager.getTileFromBackend(15, 16384, 10895);
    setState(() {
      _tileProxyWorking = tile != null;
    });
    
    // Test building data
    final buildings = await _vectorDataService.getBuildings(37.78, 37.77, -122.41, -122.42, 16);
    setState(() {
      _buildingDataWorking = buildings.isNotEmpty;
    });
    
    // Test bundle creation
    final taskId = await _bundleService.createRegionBundle(37.78, 37.77, -122.41, -122.42, 14, 16);
    setState(() {
      _bundleCreationWorking = taskId != null;
    });
    
    // Test settings sync
    final settings = await _settingsService.getMapSettings();
    setState(() {
      _settingsSyncWorking = settings != null;
    });
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Backend Diagnostics')),
      body: ListView(
        children: [
          _buildDiagnosticTile('Tile Proxy', _tileProxyWorking),
          _buildDiagnosticTile('Building Data', _buildingDataWorking),
          _buildDiagnosticTile('Region Bundles', _bundleCreationWorking),
          _buildDiagnosticTile('Settings Sync', _settingsSyncWorking),
          ElevatedButton(
            onPressed: _runDiagnostics,
            child: Text('Run Tests Again'),
          ),
        ],
      ),
    );
  }
  
  Widget _buildDiagnosticTile(String name, bool isWorking) {
    return ListTile(
      title: Text(name),
      trailing: Icon(
        isWorking ? Icons.check_circle : Icons.error,
        color: isWorking ? Colors.green : Colors.red,
      ),
    );
  }
}
```

## Graceful Degradation Strategy

To ensure your app works even when the backend is unavailable:

1. **Connection Timeouts**: Keep timeouts short (5-15 seconds)
2. **Fallback Logic**: Always fall back to direct API calls if backend fails
3. **Local Caching**: Maintain your local caching system
4. **Offline Mode Flag**: Add an offline mode flag that bypasses backend calls

Example fallback strategy:

```dart
Future<T> withFallback<T>(Future<T?> Function() backendCall, Future<T> Function() directCall) async {
  if (!Environment.shouldUseBackend()) {
    return await directCall();
  }
  
  try {
    final result = await backendCall();
    if (result != null) {
      return result;
    }
    return await directCall();
  } catch (e) {
    print('Backend error, falling back to direct: $e');
    return await directCall();
  }
}
```

## Progressive Enhancement

Instead of integrating everything at once, consider this phased approach:

1. **Phase 1**: Integrate tile proxying only
2. **Phase 2**: Add vector data endpoints
3. **Phase 3**: Implement region bundles
4. **Phase 4**: Add settings synchronization

This allows testing each component separately before moving to the next.

## Performance Monitoring

Add simple monitoring to track the effectiveness of the backend caching:

```dart
class BackendMetrics {
  static int backendTileHits = 0;
  static int backendTileMisses = 0;
  static int directApiCalls = 0;
  
  static void recordBackendTileHit() {
    backendTileHits++;
  }
  
  static void recordBackendTileMiss() {
    backendTileMisses++;
  }
  
  static void recordDirectApiCall() {
    directApiCalls++;
  }
  
  static Map<String, dynamic> getMetrics() {
    return {
      'backend_tile_hits': backendTileHits,
      'backend_tile_misses': backendTileMisses,
      'direct_api_calls': directApiCalls,
      'backend_hit_rate': backendTileHits / (backendTileHits + backendTileMisses + 0.001),
    };
  }
}
```

## API Documentation

### Tile Proxy API

- `GET /api/geo/tiles/osm/{z}/{x}/{y}.png`
  - Parameters: Standard OSM z/x/y tile coordinates
  - Returns: PNG image
  - Headers:
    - `Cache-Control`: Caching directives
    - `ETag`: Entity tag for conditional requests

### Vector Data APIs

- `GET /api/geo/buildings/`
  - Parameters:
    - `north`: Northern boundary (latitude)
    - `south`: Southern boundary (latitude)
    - `east`: Eastern boundary (longitude)
    - `west`: Western boundary (longitude)
    - `zoom`: Zoom level (controls detail level)
  - Returns: GeoJSON collection of buildings

- `GET /api/geo/roads/`
  - Similar parameters to buildings endpoint
  - Returns: GeoJSON collection of roads

- `GET /api/geo/parks/`
  - Similar parameters to buildings endpoint
  - Returns: GeoJSON collection of parks

### Region Bundle APIs

- `POST /api/geo/regions/bundle/`
  - Request Body:
    - `north`: Northern boundary
    - `south`: Southern boundary
    - `east`: Eastern boundary
    - `west`: Western boundary
    - `min_zoom`: Minimum zoom level to include
    - `max_zoom`: Maximum zoom level to include
  - Returns: 
    - `task_id`: ID to check status and download

- `GET /api/geo/regions/bundle/{task_id}/`
  - Parameters: Task ID from creation request
  - Returns:
    - If processing: Status information
    - If complete: Bundle file (ZIP)

### Map Settings API

- `GET /api/geo/settings/map/`
  - Requires authentication
  - Returns: User's map settings

- `POST /api/geo/settings/map/`
  - Requires authentication
  - Request Body: Settings object with preferences
  - Returns: Updated settings

## Troubleshooting

### Common Issues

1. **CORS Errors**
   - Ensure the backend has CORS configured to allow your app's origin
   - Solution: Check your Django settings for proper CORS configuration

2. **Authentication Issues**
   - Check if your token is being sent correctly
   - Solution: Verify headers in network requests

3. **Timeout Errors**
   - Backend may be slow to respond
   - Solution: Increase timeout duration or optimize backend performance

4. **Parsing Errors**
   - Data format mismatch between frontend and backend
   - Solution: Ensure models match the API response structure

### Diagnostic Commands

To check if the backend is working correctly:

```bash
# Check if the tile proxy is working
curl -I https://api.bopmaps.com/api/geo/tiles/osm/15/16384/10895.png

# Check if the building API is working
curl https://api.bopmaps.com/api/geo/buildings/?north=37.78&south=37.77&east=-122.41&west=-122.42&zoom=16

# Check if the settings API is working
curl -H "Authorization: Bearer YOUR_TOKEN" https://api.bopmaps.com/api/geo/settings/map/
```

## Next Steps

After basic integration, consider these enhancements:

1. **Background Synchronization**: Sync offline data when app is in background
2. **Delta Updates**: Only download changes since last sync
3. **Predictive Prefetching**: Use ML to predict user movement and prefetch data
4. **Analytics Integration**: Track usage patterns to optimize caching strategy
5. **Push Notifications**: Notify users when important map data is updated

## Conclusion

This hybrid approach gives you the best of both worlds:

- **Server Advantages**: Rate limit prevention, shared caching, cross-device sync
- **Client Advantages**: Offline usage, reduced server load, resilience

By following this integration guide, you'll enhance your existing application while maintaining its core functionality and distinctive 2.5D rendering capabilities. 