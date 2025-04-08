import 'package:flutter/material.dart';
import 'package:flutter_web_auth/flutter_web_auth.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class SpotifyAuth {
  // Your BOPMaps backend API endpoint
  final String backendUrl = 'http://your-backend-server:8000/api';
  // Your Spotify credentials (client side is safe for Client ID only)
  final String clientId = '168e3a7fcdf6491a81bb2a345e2e1870';
  // The redirect URI that's registered in your Spotify Dashboard
  final String redirectUri = 'http://localhost:8888/callback';
  
  // Authentication endpoints
  final String spotifyAuthUrl = 'https://accounts.spotify.com/authorize';
  final String spotifyTokenUrl = 'https://accounts.spotify.com/api/token';
  
  // Scopes needed for your app
  final String scopes = 'user-read-private user-read-email playlist-read-private user-library-read user-read-recently-played';

  // PKCE code verifier and challenge
  String codeVerifier = '';
  String codeChallenge = '';
  
  // Generate random string for code verifier
  String _generateRandomString(int length) {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
    return List.generate(length, (index) => chars[DateTime.now().microsecondsSinceEpoch % chars.length]).join();
  }
  
  // Generate code challenge from verifier
  String _generateCodeChallenge(String verifier) {
    // For simplicity, we're using the verifier directly
    // In a real app, you should use a proper PKCE implementation
    // that creates a SHA256 hash and base64Url encodes it
    return verifier;
  }
  
  // Initialize PKCE values
  void _initPkce() {
    codeVerifier = _generateRandomString(128);
    codeChallenge = _generateCodeChallenge(codeVerifier);
  }
  
  // Start the Spotify authentication flow
  Future<Map<String, dynamic>> authenticate() async {
    try {
      // Initialize PKCE
      _initPkce();
      
      // Build the authorization URL
      final authUrl = Uri.parse(spotifyAuthUrl).replace(
        queryParameters: {
          'client_id': clientId,
          'response_type': 'code',
          'redirect_uri': redirectUri,
          'scope': scopes,
          'code_challenge_method': 'S256',
          'code_challenge': codeChallenge,
        },
      ).toString();
      
      // Launch the authentication flow in a WebView
      final result = await FlutterWebAuth.authenticate(
        url: authUrl,
        callbackUrlScheme: 'bopmaps', // This should match your app's registered URL scheme
      );
      
      // Parse the result URL to get the authorization code
      final uri = Uri.parse(result);
      final code = uri.queryParameters['code'];
      
      if (code == null) {
        throw Exception('No authorization code received');
      }
      
      // Send the code to your backend to exchange for tokens
      final response = await http.post(
        Uri.parse('$backendUrl/music/auth/callback/'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'code': code,
          'code_verifier': codeVerifier,
          'redirect_uri': redirectUri,
        }),
      );
      
      if (response.statusCode != 200) {
        throw Exception('Failed to exchange code for tokens: ${response.body}');
      }
      
      return json.decode(response.body);
    } catch (e) {
      print('Error during Spotify authentication: $e');
      return {'error': e.toString()};
    }
  }
}

// Example usage in a Flutter widget
class SpotifyLoginButton extends StatelessWidget {
  final SpotifyAuth _auth = SpotifyAuth();
  
  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: () async {
        final result = await _auth.authenticate();
        if (result.containsKey('error')) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Authentication error: ${result['error']}')),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Authentication successful!')),
          );
          
          // Navigate to the next screen or update UI
          Navigator.of(context).pushReplacementNamed('/home');
        }
      },
      child: Text('Connect with Spotify'),
    );
  }
} 