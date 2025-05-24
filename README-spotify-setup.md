# Spotify Authentication Setup Guide

This guide explains how to set up the Spotify authentication flow using the Spotify SDK for Flutter, which then sends authentication data to your backend.

## Architecture Overview

The authentication flow works as follows:

1. **Flutter App**: Uses Spotify SDK to authenticate with Spotify
2. **Spotify**: Returns access token and user data to Flutter app
3. **Flutter App**: Sends Spotify token and user data to your backend
4. **Backend**: Validates Spotify token, creates/updates user, returns app auth token
5. **Flutter App**: Uses backend auth token for subsequent API calls

## Flutter Setup

### 1. Update Spotify Configuration

In `BOPMaps/lib/screens/auth/login_screen.dart`, update these constants with your actual Spotify app credentials:

```dart
static const String _spotifyClientId = "your_actual_spotify_client_id";
static const String _spotifyRedirectUrl = "bopmaps://auth"; // or your custom scheme
```

### 2. Add Spotify SDK Dependency

Make sure `spotify_sdk` is in your `pubspec.yaml`:

```yaml
dependencies:
  spotify_sdk: ^3.0.2
```

### 3. Configure Platform-Specific Settings

#### Android Setup

1. **Add to `android/app/src/main/AndroidManifest.xml`**:
```xml
<activity
    android:name="com.spotify.sdk.android.authentication.AuthenticationActivity"
    android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="bopmaps" android:host="callback" />
    </intent-filter>
</activity>
```

2. **Run the Spotify setup script** (if available):
```bash
dart run spotify_sdk:android_setup
```

#### iOS Setup

1. **Add to `ios/Runner/Info.plist`**:
```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLName</key>
        <string>Spotify Authentication</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>bopmaps</string>
        </array>
    </dict>
</array>
```

2. **Add Spotify SDK to your iOS project** following the [Spotify iOS SDK documentation](https://developer.spotify.com/documentation/ios/).

## Spotify App Configuration

### 1. Create Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Note your **Client ID**

### 2. Configure Redirect URIs

Add these redirect URIs to your Spotify app:

- `bopmaps://callback` (matches the current implementation)
- `bopmaps://auth` (alternative)
- `http://localhost:8888/callback` (for testing)

### 3. Set Required Scopes

The app requests these scopes:
- `app-remote-control`: Control Spotify app
- `user-modify-playback-state`: Control playback
- `playlist-read-private`: Read private playlists
- `user-library-read`: Read saved tracks
- `user-read-email`: Read user email
- `user-read-private`: Read user profile
- `user-read-recently-played`: Read recently played tracks
- `user-top-read`: Read top tracks/artists

## Important Notes

### Preventing Auto-Play
The implementation uses an undocumented workaround to prevent Spotify from automatically playing music when connecting:

```dart
final connectionSuccess = await SpotifySdk.connectToSpotifyRemote(
  clientId: _spotifyClientId,
  redirectUrl: _spotifyRedirectUrl,
  playUri: "spotify:track:invalid", // Invalid URI prevents auto-play
);
```

### App-to-App Authentication
The flow prioritizes app-to-app authentication (no web view) by:
1. First connecting to Spotify Remote (uses Spotify app if installed)
2. Then getting access token for API calls
3. Falling back gracefully if web authentication is needed

## Backend Integration

### 1. Create Spotify Auth Endpoint

Create an endpoint at `/api/auth/spotify/` that accepts:

```json
{
  "access_token": "spotify_access_token",
  "user_id": "spotify_user_id",
  "display_name": "User Name",
  "email": "user@email.com",
  "profile_image_url": "https://...",
  "country": "US",
  "followers": 1234,
  "is_premium": true
}
```

### 2. Backend Response Format

Your backend should return:

```json
{
  "auth_token": "your_app_auth_token",
  "user": {
    "id": "user_id_in_your_system",
    "name": "User Name",
    "email": "user@email.com",
    "profile_image_url": "https://...",
    "bio": "User bio"
  }
}
```

### 3. Example Django Backend Implementation

```python
# views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
import requests

@api_view(['POST'])
def spotify_auth(request):
    access_token = request.data.get('access_token')
    
    # Verify token with Spotify
    headers = {'Authorization': f'Bearer {access_token}'}
    spotify_response = requests.get(
        'https://api.spotify.com/v1/me',
        headers=headers
    )
    
    if spotify_response.status_code != 200:
        return Response({'error': 'Invalid Spotify token'}, status=400)
    
    spotify_user = spotify_response.json()
    
    # Create or update user in your system
    user, created = User.objects.get_or_create(
        spotify_id=spotify_user['id'],
        defaults={
            'name': spotify_user.get('display_name'),
            'email': spotify_user.get('email'),
            'profile_image_url': spotify_user.get('images', [{}])[0].get('url'),
            'is_premium': spotify_user.get('product') == 'premium',
        }
    )
    
    # Generate your app's auth token
    from rest_framework.authtoken.models import Token
    token, created = Token.objects.get_or_create(user=user)
    
    return Response({
        'auth_token': token.key,
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'profile_image_url': user.profile_image_url,
            'bio': user.bio,
        }
    })
```

## API Client Configuration

Update the API client base URL in `login_screen.dart`:

```dart
class ApiClient {
  final String baseUrl = "https://your-actual-domain.com"; // Update this
  // ... rest of the implementation
}
```

## Testing

### 1. Test Spotify Authentication

1. Make sure your Spotify app credentials are correct
2. Test the redirect URI setup
3. Verify you can get an access token

### 2. Test Backend Integration

1. Test the `/api/auth/spotify/` endpoint manually
2. Verify token validation works
3. Check user creation/update logic

### 3. Test Full Flow

1. Run the Flutter app
2. Tap "Continue with Spotify"
3. Complete Spotify authentication
4. Verify backend receives the data
5. Check that the app navigates to the map screen

## Troubleshooting

### Common Issues

1. **"Invalid client_id"**: Check your Spotify Client ID
2. **"Invalid redirect URI"**: Ensure redirect URI matches exactly
3. **"Network Error"**: Check backend URL and endpoint
4. **"Token validation failed"**: Verify Spotify token is being sent correctly

### Debug Logging

Enable debug logging to see the authentication flow:

```dart
if (kDebugMode) {
  print('🎵 Debug info here');
}
```

### Fallback Behavior

The app includes fallback behavior:
- If backend auth fails, it continues with local authentication
- Users can still use the app in demo mode

## Security Considerations

1. **Never expose your Spotify Client Secret** in the Flutter app
2. **Validate Spotify tokens** on your backend
3. **Use HTTPS** for all backend communication
4. **Implement token refresh** logic
5. **Handle token expiration** gracefully

## Production Deployment

1. Update redirect URIs for production domains
2. Configure production backend URLs
3. Test authentication flow in production environment
4. Monitor authentication success rates
5. Implement proper error reporting

## Support

- [Spotify SDK Flutter Documentation](https://pub.dev/packages/spotify_sdk)
- [Spotify Web API Documentation](https://developer.spotify.com/documentation/web-api/)
- [Spotify App Development Guide](https://developer.spotify.com/documentation/android/) 