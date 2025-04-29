# 🎵 BOPMaps Backend Documentation

**Version:** 1.0  
## Lead Devs: Jah
## CO Dev: Mothuso
  


**Stack:** Django REST Framework (Backend) • Flutter(Frontend) • Spotify/Apple/Soundcloud APIs • Geolocation & Leaflet.js Maps

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

## 🎵 Spotify Integration

### Overview
BOPMaps integrates with the Spotify API to allow users to:
1. Connect their Spotify accounts via OAuth 2.0
2. Search for and share Spotify tracks as pins
3. Access their playlists and recently played tracks
4. Play previews or open tracks in Spotify

### Setup and Authentication
1. **OAuth 2.0 Flow**:
   - Users initiate authentication via `/api/music/auth/spotify/`
   - After authorizing, Spotify redirects to our callback at `/api/music/auth/spotify/callback/`
   - Access and refresh tokens are securely stored in the `MusicService` model

2. **Environment Variables**:
   ```
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   ```

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/music/auth/spotify/` | GET | Initiate Spotify OAuth flow |
| `/api/music/auth/spotify/callback/` | GET | OAuth callback handler |
| `/api/music/api/services/` | GET | Get connected music services |
| `/api/music/api/spotify/playlists/` | GET | Get user's Spotify playlists |
| `/api/music/api/spotify/playlist/{id}/` | GET | Get playlist details |
| `/api/music/api/spotify/playlist/{id}/tracks/` | GET | Get playlist tracks |
| `/api/music/api/spotify/track/{id}/` | GET | Get track details |
| `/api/music/api/spotify/recently_played/` | GET | Get recently played tracks |
| `/api/music/api/spotify/search/` | GET | Search Spotify tracks |
| `/api/music/api/tracks/search/` | GET | Search tracks across all services |
| `/api/music/api/tracks/recently_played/` | GET | Get recently played across all services |

### Data Models
The music integration is built around two main models:

1. **MusicService**:
   ```python
   class MusicService(models.Model):
       user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='music_services')
       service_type = models.CharField(max_length=20, choices=[('spotify', 'Spotify'), ...])
       access_token = models.CharField(max_length=1024)
       refresh_token = models.CharField(max_length=1024, blank=True, null=True)
       expires_at = models.DateTimeField()
   ```

2. **RecentTrack**:
   ```python
   class RecentTrack(models.Model):
       user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recent_tracks')
       track_id = models.CharField(max_length=255)
       title = models.CharField(max_length=255)
       artist = models.CharField(max_length=255)
       album = models.CharField(max_length=255, blank=True, null=True)
       album_art = models.URLField(blank=True, null=True)
       service = models.CharField(max_length=20, choices=MusicService.SERVICE_TYPES)
       played_at = models.DateTimeField()
   ```

### Functionality
1. **Track Search**: Search across Spotify's catalog by title, artist, or album
2. **Recently Played**: Fetch and store user's recently played tracks
3. **Playlist Access**: Browse and select tracks from user's playlists
4. **Token Refresh**: Automatic refresh of expired access tokens
5. **Error Handling**: Graceful handling of API errors and rate limits

### Pin Integration
When creating pins, users can select Spotify tracks with these fields:
- `track_title`: Title of the track
- `track_artist`: Artist name
- `album`: Album name (optional)
- `track_url`: Spotify URL to the track
- `service`: Set to 'spotify'

### Frontend Integration
The frontend can access these endpoints to:
1. Display a track selection interface when creating pins
2. Show track details with album art when viewing pins
3. Provide play buttons that open tracks in Spotify
4. Display the user's playlists and recently played tracks

### Documentation
For detailed setup instructions and troubleshooting, see:
- [README-spotify.md](README-spotify.md) - Comprehensive setup guide
- API documentation at `/api/schema/swagger-ui/`

---

## 🎵 Flutter Frontend Spotify Integration

### Overview
This section outlines how to integrate Spotify into your BOPMaps Flutter frontend, leveraging the backend API endpoints.

### Required Dependencies
Add these to your `pubspec.yaml`:
```yaml
dependencies:
  spotify_sdk: ^2.3.0        # Native Spotify SDK integration
  flutter_web_auth: ^0.5.0   # OAuth flow in WebView
  http: ^0.13.5              # HTTP requests
  flutter_secure_storage: ^8.0.0  # Secure token storage
```

### Main Components

#### 1. MusicTrack Model
```dart
class MusicTrack {
  final String id;
  final String title; 
  final String artist;
  final String album;
  final String albumArt;
  final String url;
  final String service;
  final String? previewUrl;
  
  MusicTrack({
    required this.id,
    required this.title,
    required this.artist,
    required this.album,
    required this.albumArt,
    required this.url,
    required this.service,
    this.previewUrl,
  });
  
  factory MusicTrack.fromJson(Map<String, dynamic> json) {
    return MusicTrack(
      id: json['id'],
      title: json['title'],
      artist: json['artist'],
      album: json['album'] ?? '',
      albumArt: json['album_art'] ?? '',
      url: json['url'],
      service: json['service'],
      previewUrl: json['preview_url'],
    );
  }
  
  // Helper to generate pin data
  Map<String, dynamic> toPinData({
    required String title,
    required String description,
    required double latitude,
    required double longitude,
  }) {
    return {
      'title': title,
      'description': description,
      'location': {
        'type': 'Point',
        'coordinates': [longitude, latitude]
      },
      'track_title': this.title,
      'track_artist': this.artist, 
      'album': this.album,
      'track_url': this.url,
      'service': this.service,
    };
  }
}
```

#### 2. SpotifyService Class
```dart
class SpotifyService {
  final ApiClient _apiClient;
  
  SpotifyService({required ApiClient apiClient}) : _apiClient = apiClient;
  
  /// Check if user has connected Spotify
  Future<bool> isConnected() async {
    try {
      final response = await _apiClient.get('/api/music/api/services/');
      final services = List<Map<String, dynamic>>.from(response.data);
      return services.any((service) => service['service_type'] == 'spotify');
    } catch (e) {
      print('Error checking Spotify connection: $e');
      return false;
    }
  }
  
  /// Connect Spotify using OAuth
  Future<bool> connect() async {
    try {
      // Get auth URL from our backend
      final response = await _apiClient.get('/api/music/auth/spotify/');
      final authUrl = response.data['auth_url'];
      
      // Launch OAuth flow in WebView
      final result = await FlutterWebAuth.authenticate(
        url: authUrl,
        callbackUrlScheme: 'bopmaps', // Must match registered callback URL
      );
      
      // Extract the authorization code
      final code = Uri.parse(result).queryParameters['code'];
      if (code == null) {
        throw Exception('Authorization code not found');
      }
      
      // Send code to backend to exchange for tokens
      await _apiClient.post(
        '/api/music/auth/spotify/callback/',
        data: {'code': code},
      );
      
      return true;
    } catch (e) {
      print('Error connecting to Spotify: $e');
      return false;
    }
  }
  
  /// Search for tracks
  Future<List<MusicTrack>> searchTracks(String query) async {
    try {
      final response = await _apiClient.get(
        '/api/music/api/tracks/search/',
        queryParameters: {'q': query},
      );
      
      final spotifyResults = response.data['spotify'] ?? [];
      return List<MusicTrack>.from(
        spotifyResults.map((track) => MusicTrack.fromJson(track))
      );
    } catch (e) {
      print('Error searching tracks: $e');
      return [];
    }
  }
  
  /// Get recently played tracks
  Future<List<MusicTrack>> getRecentlyPlayed({int limit = 20}) async {
    try {
      final response = await _apiClient.get(
        '/api/music/api/tracks/recently_played/',
        queryParameters: {'limit': limit.toString()},
      );
      
      final spotifyResults = response.data['spotify'] ?? [];
      return List<MusicTrack>.from(
        spotifyResults.map((track) => MusicTrack.fromJson(track))
      );
    } catch (e) {
      print('Error getting recently played: $e');
      return [];
    }
  }
  
  /// Get user's playlists
  Future<List<Map<String, dynamic>>> getPlaylists() async {
    try {
      final response = await _apiClient.get('/api/music/api/spotify/playlists/');
      
      if (response.data['items'] != null) {
        return List<Map<String, dynamic>>.from(response.data['items']);
      }
      return [];
    } catch (e) {
      print('Error getting playlists: $e');
      return [];
    }
  }
  
  /// Get tracks from a playlist
  Future<List<MusicTrack>> getPlaylistTracks(String playlistId) async {
    try {
      final response = await _apiClient.get(
        '/api/music/api/spotify/playlist/$playlistId/tracks/'
      );
      
      if (response.data['items'] != null) {
        final trackItems = List<Map<String, dynamic>>.from(response.data['items']);
        return trackItems.map((item) {
          final track = item['track'];
          return MusicTrack(
            id: track['id'],
            title: track['name'],
            artist: track['artists'][0]['name'],
            album: track['album']['name'],
            albumArt: track['album']['images'][0]['url'],
            url: track['external_urls']['spotify'],
            service: 'spotify',
          );
        }).toList();
      }
      return [];
    } catch (e) {
      print('Error getting playlist tracks: $e');
      return [];
    }
  }
  
  /// Play a track using Spotify app
  Future<bool> playTrack(String trackUri) async {
    try {
      await SpotifySdk.connectToSpotifyRemote(
        clientId: "YOUR_CLIENT_ID",
        redirectUrl: "bopmaps://callback",
      );
      
      await SpotifySdk.play(spotifyUri: trackUri);
      return true;
    } catch (e) {
      print('Error playing track: $e');
      return false;
    }
  }
}
```

#### 3. MusicProvider (State Management)
```dart
class MusicProvider with ChangeNotifier {
  final SpotifyService _spotifyService;
  
  bool _isSpotifyConnected = false;
  List<MusicTrack> _searchResults = [];
  List<MusicTrack> _recentTracks = [];
  List<Map<String, dynamic>> _playlists = [];
  MusicTrack? _selectedTrack;
  bool _isLoading = false;
  
  MusicProvider({required SpotifyService spotifyService}) 
    : _spotifyService = spotifyService {
    _checkConnections();
  }
  
  // Getters
  bool get isSpotifyConnected => _isSpotifyConnected;
  List<MusicTrack> get searchResults => _searchResults;
  List<MusicTrack> get recentTracks => _recentTracks;
  List<Map<String, dynamic>> get playlists => _playlists;
  MusicTrack? get selectedTrack => _selectedTrack;
  bool get isLoading => _isLoading;
  
  // Methods
  Future<void> _checkConnections() async {
    _isLoading = true;
    notifyListeners();
    
    _isSpotifyConnected = await _spotifyService.isConnected();
    
    _isLoading = false;
    notifyListeners();
  }
  
  Future<bool> connectSpotify() async {
    _isLoading = true;
    notifyListeners();
    
    final result = await _spotifyService.connect();
    if (result) {
      _isSpotifyConnected = true;
    }
    
    _isLoading = false;
    notifyListeners();
    return result;
  }
  
  Future<void> searchTracks(String query) async {
    if (query.trim().isEmpty) {
      _searchResults = [];
      notifyListeners();
      return;
    }
    
    _isLoading = true;
    notifyListeners();
    
    _searchResults = await _spotifyService.searchTracks(query);
    
    _isLoading = false;
    notifyListeners();
  }
  
  void selectTrack(MusicTrack track) {
    _selectedTrack = track;
    notifyListeners();
  }
}
```

### Integration with Pin Creation
Integrate track selection when creating pins:

```dart
class CreatePinScreen extends StatefulWidget {
  @override
  _CreatePinScreenState createState() => _CreatePinScreenState();
}

class _CreatePinScreenState extends State<CreatePinScreen> {
  MusicTrack? _selectedTrack;
  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _descriptionController = TextEditingController();
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Drop a Music Pin')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Pin details form
            TextField(
              controller: _titleController,
              decoration: InputDecoration(labelText: 'Pin Title'),
            ),
            TextField(
              controller: _descriptionController,
              decoration: InputDecoration(labelText: 'Description'),
              maxLines: 2,
            ),
            
            SizedBox(height: 16),
            
            // Track selection button
            ElevatedButton(
              onPressed: () => _selectTrack(context),
              child: Text('Select Music Track'),
            ),
            
            // Selected track preview
            if (_selectedTrack != null) ...[
              SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12.0),
                  child: Row(
                    children: [
                      Image.network(
                        _selectedTrack!.albumArt,
                        width: 60,
                        height: 60,
                      ),
                      SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _selectedTrack!.title,
                              style: TextStyle(fontWeight: FontWeight.bold),
                            ),
                            Text(_selectedTrack!.artist),
                            Text(
                              'via ${_selectedTrack!.service}',
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.grey[600],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            
            Spacer(),
            
            // Submit button
            ElevatedButton(
              onPressed: _selectedTrack == null ? null : _createPin,
              child: Text('Drop Pin'),
              style: ElevatedButton.styleFrom(
                padding: EdgeInsets.symmetric(vertical: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }
  
  void _selectTrack(BuildContext context) async {
    final MusicTrack? track = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => TrackSearchScreen(),
      ),
    );
    
    if (track != null) {
      setState(() {
        _selectedTrack = track;
        // Optionally set title based on track
        if (_titleController.text.isEmpty) {
          _titleController.text = '${track.title} by ${track.artist}';
        }
      });
    }
  }
  
  void _createPin() {
    // Get current location
    final currentLocation = Provider.of<LocationProvider>(context, listen: false).currentLocation;
    
    if (currentLocation == null || _selectedTrack == null) return;
    
    // Create pin data
    final pinData = _selectedTrack!.toPinData(
      title: _titleController.text,
      description: _descriptionController.text,
      latitude: currentLocation.latitude,
      longitude: currentLocation.longitude,
    );
    
    // Save pin to backend
    Provider.of<PinProvider>(context, listen: false)
        .createPin(pinData)
        .then((_) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Pin dropped successfully!')),
      );
      Navigator.pop(context);
    }).catchError((error) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: ${error.toString()}')),
      );
    });
  }
}
```

### Track Search Screen
Create a screen for searching and selecting music:

```dart
class TrackSearchScreen extends StatefulWidget {
  @override
  _TrackSearchScreenState createState() => _TrackSearchScreenState();
}

class _TrackSearchScreenState extends State<TrackSearchScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final TextEditingController _searchController = TextEditingController();
  
  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    
    // Load initial data
    Future.microtask(() {
      final musicProvider = Provider.of<MusicProvider>(context, listen: false);
      musicProvider.fetchRecentlyPlayed();
      musicProvider.fetchPlaylists();
    });
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Select Music'),
        bottom: TabBar(
          controller: _tabController,
          tabs: [
            Tab(text: 'Search'),
            Tab(text: 'Recent'),
            Tab(text: 'Playlists'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          // Search tab
          Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(16.0),
                child: TextField(
                  controller: _searchController,
                  decoration: InputDecoration(
                    labelText: 'Search for music',
                    prefixIcon: Icon(Icons.search),
                    border: OutlineInputBorder(),
                  ),
                  onChanged: (value) {
                    if (value.length > 2) {
                      Provider.of<MusicProvider>(context, listen: false)
                          .searchTracks(value);
                    }
                  },
                ),
              ),
              Expanded(
                child: Consumer<MusicProvider>(
                  builder: (context, provider, child) {
                    if (provider.isLoading) {
                      return Center(child: CircularProgressIndicator());
                    }
                    
                    return ListView.builder(
                      itemCount: provider.searchResults.length,
                      itemBuilder: (context, index) {
                        final track = provider.searchResults[index];
                        return ListTile(
                          leading: Image.network(track.albumArt),
                          title: Text(track.title),
                          subtitle: Text(track.artist),
                          onTap: () {
                            Navigator.pop(context, track);
                          },
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
          
          // Recent tab
          Consumer<MusicProvider>(
            builder: (context, provider, child) {
              if (!provider.isSpotifyConnected) {
                return Center(
                  child: ElevatedButton(
                    onPressed: () => provider.connectSpotify(),
                    child: Text('Connect to Spotify'),
                  ),
                );
              }
              
              if (provider.isLoading) {
                return Center(child: CircularProgressIndicator());
              }
              
              return ListView.builder(
                itemCount: provider.recentTracks.length,
                itemBuilder: (context, index) {
                  final track = provider.recentTracks[index];
                  return ListTile(
                    leading: Image.network(track.albumArt),
                    title: Text(track.title),
                    subtitle: Text(track.artist),
                    onTap: () {
                      Navigator.pop(context, track);
                    },
                  );
                },
              );
            },
          ),
          
          // Playlists tab (similar implementation)
          Center(child: Text('Playlists')),
        ],
      ),
    );
  }
}
```

### Setup in main.dart
Properly initialize services and providers:

```dart
void main() {
  runApp(
    MultiProvider(
      providers: [
        Provider<ApiClient>(
          create: (_) => ApiClient(),
        ),
        Provider<SpotifyService>(
          create: (context) => SpotifyService(
            apiClient: context.read<ApiClient>(),
          ),
        ),
        ChangeNotifierProvider<MusicProvider>(
          create: (context) => MusicProvider(
            spotifyService: context.read<SpotifyService>(),
          ),
        ),
        // Other providers...
      ],
      child: MyApp(),
    ),
  );
}
```

### Handling Deep Links
Configure your app to handle Spotify OAuth callbacks:

1. **In Android (android/app/src/main/AndroidManifest.xml)**:
```xml
<intent-filter>
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="bopmaps" android:host="callback" />
</intent-filter>
```

2. **In iOS (ios/Runner/Info.plist)**:
```xml
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleTypeRole</key>
    <string>Editor</string>
    <key>CFBundleURLName</key>
    <string>com.yourdomain.bopmaps</string>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>bopmaps</string>
    </array>
  </dict>
</array>
```

By following this implementation, you'll have a complete Spotify integration in your Flutter frontend that communicates seamlessly with your Django backend.

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

### Web Pages
```
GET    /music/connect/                # GET - Page for connecting music services
GET    /music/auth/spotify/           # GET - Start Spotify OAuth flow
GET    /music/auth/spotify/callback/  # GET - Spotify OAuth callback
GET    /music/auth/success/           # GET - Successful connection page
```

### Music Service Management
```
GET    /music/api/services/connected_services/        # GET - Get connected services
DELETE /music/api/services/disconnect/{service_type}/   # DELETE - Disconnect service
```

### Spotify-specific APIs
```
GET    /music/api/spotify/playlists/                  # GET - Get user playlists
GET    /music/api/spotify/playlist/{id}/              # GET - Get playlist details
GET    /music/api/spotify/playlist/{id}/tracks/       # GET - Get playlist tracks
GET    /music/api/spotify/track/{id}/                 # GET - Get track details
GET    /music/api/spotify/recently_played/            # GET - Get recently played
GET    /music/api/spotify/search/                     # GET - Search Spotify tracks
```

### Generic Track APIs (work across multiple services)
```
GET    /music/api/tracks/search/                      # GET - Search across all services
GET    /music/api/tracks/recently_played/             # GET - Get recently played from all
GET    /music/api/tracks/playlists/                   # GET - Get playlists from all
GET    /music/api/tracks/playlist/{service}/{id}/     # GET - Get tracks from a playlist
GET    /music/api/tracks/track/{service}/{id}/        # GET - Get track details
```

### Friends
```
GET    /friends/
POST   /friends/requests/
```

### Geo
```
GET    /geo/trending/                 // GET - Get trending areas
GET    /geo/trending/map_visualization/ // GET - Get data for heatmap visualization
GET    /geo/locations/                // GET - User location data

// WebSocket for real-time location
WS_BASE_URL + "/ws/location/"                   // WebSocket for location updates
```

### Gamification
```
GET    /gamification/achievements/    // GET - List achievements
GET    /gamification/badges/          // GET - List badges
```

### API Documentation
```
GET    /schema/                       // GET - OpenAPI schema
GET    /schema/swagger-ui/            // GET - Swagger UI
GET    /schema/redoc/                 // GET - ReDoc UI
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

BASE_URL = "http://your-server-address:8000"  // Replace with your actual server address
API_BASE_URL = BASE_URL + "/api" 
