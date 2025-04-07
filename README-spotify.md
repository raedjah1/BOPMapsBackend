# Spotify Integration for BOPMaps

This guide walks you through setting up Spotify integration for your BOPMaps application.

## Prerequisites

1. A Spotify account (free or premium)
2. Access to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)

## Step 1: Create a Spotify App

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Log in with your Spotify account
3. Click **Create an App**
4. Fill in the required information:
   - App name: `BOPMaps` (or your preferred name)
   - App description: `A music geo-social platform for sharing music at specific locations`
   - Website: `http://localhost:8000` (for development) or your production URL
   - Redirect URI: `http://localhost:8000/api/music/auth/spotify/callback/` (replace with your domain in production)
5. Check the terms and conditions box and click **Create**

## Step 2: Get Your Client ID and Secret

1. After creating your app, you'll be redirected to your app's dashboard
2. Note down the **Client ID** and **Client Secret**
3. Click **Edit Settings** and add the redirect URI:
   - `http://localhost:8000/api/music/auth/spotify/callback/`
4. Click **Save**

## Step 3: Configure Your Environment Variables

Add the following variables to your `.env` file:

```
# Spotify API Credentials
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

Replace `your_client_id_here` and `your_client_secret_here` with the values from your Spotify app dashboard.

## Step 4: Test the Integration

1. Start your Django server:
   ```
   python manage.py runserver
   ```

2. Visit the music connection page:
   ```
   http://localhost:8000/api/music/connect/
   ```

3. Click on "Connect Spotify" and authorize your application

4. After successful authorization, you should be redirected to the success page, and your Spotify account will be connected to BOPMaps.

## Common Issues and Troubleshooting

### Invalid Redirect URI

If you encounter an error saying "Invalid redirect URI" during the OAuth flow, ensure that:

1. The redirect URI in your Spotify app settings exactly matches the one used in your application
2. There are no trailing slashes or typos in the URI
3. The URI is using the correct protocol (http/https)

### Access Token Issues

If you encounter issues with expired tokens or refresh token failures:

1. Check that your client secret is correctly set in your environment variables
2. Ensure your server's clock is synchronized (OAuth relies on accurate timestamps)
3. Try reconnecting your Spotify account by disconnecting and connecting again

### API Rate Limiting

Spotify has rate limits for API calls. If you encounter errors related to rate limiting:

1. Implement caching for frequently accessed data
2. Use the refresh token flow properly to avoid unnecessary token refreshes
3. Consider adding throttling to your API endpoints

## Using the API

Once connected, you can use the following API endpoints:

- Get user's playlists: `GET /api/music/api/tracks/playlists/`
- Search for tracks: `GET /api/music/api/tracks/search/?q=search_term`
- Get recently played: `GET /api/music/api/tracks/recently_played/`
- Get playlist tracks: `GET /api/music/api/tracks/playlist/spotify/playlist_id/`

For more information on the available endpoints, refer to the API documentation.

## Next Steps

After successfully setting up Spotify, you can:

1. Implement Apple Music integration following a similar pattern
2. Add SoundCloud integration
3. Enhance the UI for selecting tracks when creating pins 