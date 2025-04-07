# POVBackend

## Features

- User Management:
  - User registration and authentication
  - Support for multiple sign-in methods (email, Google, Facebook, Apple)
  - User profile management

- Content Management:
  - Upload and manage video content ("visions")
  - Support for live streaming
  - Comment system on videos
  - Like/dislike functionality for videos

- Creator Features:
  - Creator profiles
  - Subscription system for creators
  - Analytics for creator content

- Discovery:
  - Recommendation system for content
  - Search functionality for visions and creators
  - Trending content algorithm

- Events:
  - Create and manage live events
  - Event reminders for users

- Subscriptions:
  - Subscription management for users
  - Pricing management for creators

- Payments:
  - Integration with Stripe for payment processing
  - Support for subscriptions and one-time payments (tips)

- Interest-based Content:
  - Tag content with interests
  - Personalized content based on user interests

## AWS Live Streaming Architecture

![image](https://github.com/user-attachments/assets/691f8978-6a55-4bdc-8135-e3da18c58e69)

This architecture outlines a scalable & cost-effective video streaming platform using AWS services:

1. Content Creation: Creators requests a video stream id from the Django server. Their camera streams to the transcoding environment via RTMP

2. Processing:
   - Python Django Server: Handles user data and metadata management.
   - Adaptive Bitrate Transcoding: Uses FFmpeg to create multiple quality versions of each video.
   - Both components run in Elastic Beanstalk with Auto Scaling for handling varying loads.

3. Storage:
   - Amazon RDS: Stores metadata and user information.
   - Storage Bucket (S3 equivalent): Stores processed video files. Once a stream is completed, it will be available as video on-demand

4. Distribution:
   - Content Delivery Network (CDN): Efficiently delivers video content to viewers globally. We are using Cloudflare CDN.

5. Additional Features:
   - Lambda function: Triggers content moderation tasks on streams at a regular interval
   - Amazon Rekognition: Performs automated content moderation for explicit content

6. Load Balancing:
   - Application Load Balancer: Distributes incoming traffic to the Django server.
   - Network Load Balancer: Manages traffic for the transcoding service.

7. Caching:
   - Amazon ElastiCache: Improves performance by caching frequently accessed data.

This setup ensures scalability and efficient content delivery while providing tools for content management and moderation.

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/your-repo/pov-backend.git
   cd pov-backend
   ```

2. Set up a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up your environment variables:
   - Create a `.env` file in the project root
   - Add necessary environment variables (see Configuration section)

5. Run migrations:
   ```
   python manage.py migrate
   ```

6. Start the development server:
   ```
   python manage.py runserver
   ```

## Usage

After starting the server, you can interact with the API using tools like cURL, Postman, or any HTTP client. The API endpoints are grouped into several categories:

- Users: `/users/`
- Visions (Videos): `/visions/`
- Events: `/events/`
- Subscriptions: `/subscriptions/`
- Payments: `/payments/`

Refer to the API documentation for detailed information on each endpoint.

## Configuration

The following environment variables need to be set in your `.env` file:

- `SECRET_KEY`: Django secret key
- `DEBUG`: Set to True for development, False for production
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts
- `DATABASE_URL`: URL for your database connection
- `STRIPE_SECRET_KEY`: Your Stripe secret key
- `STRIPE_PUBLISHABLE_KEY`: Your Stripe publishable key
- `GOOGLE_OAUTH_CLIENT_ID`: Google OAuth client ID
- `FACEBOOK_APP_ID`: Facebook App ID
- `FACEBOOK_APP_SECRET`: Facebook App Secret
- `APPLE_KEY_ID`: Apple Key ID
- `APPLE_TEAM_ID`: Apple Team ID
- `APPLE_CLIENT_ID`: Apple Client ID
- `APPLE_PRIVATE_KEY`: Apple Private Key
- `AWS_ACCESS_KEY_ID`: AWS access key for S3
- `AWS_SECRET_ACCESS_KEY`: AWS secret key for S3
- `AWS_STORAGE_BUCKET_NAME`: S3 bucket name
- `CLOUDINARY_CLOUD_NAME`: Cloudinary cloud name
- `CLOUDINARY_API_KEY`: Cloudinary API key
- `CLOUDINARY_API_SECRET`: Cloudinary API secret

Ensure all these environment variables are properly set before running the application.

## API Documentation

### Users Endpoints

#### Update Profile Picture
- **POST /users/update-profile-picture/**
  - Description: Updates the user's profile picture.
  - Authentication: Required (Token Authentication)
  - Request:
    ```
    Content-Type: multipart/form-data
    Authorization: Token <user_token>

    profile_picture: <file>
    ```
  - Response:
    ```json
    {
      "message": "Profile picture updated successfully",
      "profile_picture": "https://example.com/profile_picture_url.jpg"
    }
    ```

#### Get Interests
- **GET /users/interest/**
  - Description: Retrieves a paginated list of all interests.
  - Authentication: Not required
  - Response:
    ```json
    {
      "data": [
        {
          "id": 1,
          "name": "Technology"
        },
        {
          "id": 2,
          "name": "Sports"
        }
      ],
      "size": 20,
      "next": "http://example.com/users/interest/?page=2",
      "prev": null
    }
    ```

#### Add or Remove Interest from Spectator
- **POST /users/add-remove-interest/**
  - Description: Adds or removes interests for a spectator user.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "interests": ["Technology", "Sports"]
    }
    ```
  - Response:
    ```json
    {
      "message": "Interests added to spectator successfully!"
    }
    ```

#### Search Interests
- **POST /users/search-interests/**
  - Description: Searches for interests based on a query.
  - Authentication: Not required
  - Request:
    ```json
    {
      "search_text": "tech"
    }
    ```
  - Response:
    ```json
    {
      "message": "Interests found",
      "data": [
        {
          "id": 1,
          "name": "Technology"
        },
        {
          "id": 5,
          "name": "Biotechnology"
        }
      ]
    }
    ```

#### Get or Create Interests
- **POST /users/get-create-interests/**
  - Description: Gets existing interests or creates new ones if they don't exist.
  - Authentication: Not required
  - Request:
    ```json
    {
      "interests": ["Technology", "New Interest"]
    }
    ```
  - Response:
    ```json
    {
      "interests": [
        {
          "id": 1,
          "name": "Technology"
        },
        {
          "id": 10,
          "name": "New Interest"
        }
      ]
    }
    ```

#### Create Creator Account
- **POST /users/create-creator-account/**
  - Description: Creates a creator account for an existing user.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "subscription_price": 9.99,
      "bio": "I create awesome content!"
    }
    ```
  - Response:
    ```json
    {
      "message": "Creator account created successfully",
      "data": {
        "user": 1,
        "subscription_price": 9.99,
        "subscriber_count": 0,
        "bio": "I create awesome content!",
        "is_verified": false,
        "subscription_price_id": null
      }
    }
    ```

#### Creator Account Detail
- **GET /users/creator-account/**
  - Description: Retrieves details of the authenticated user's creator account.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "data": {
        "user": 1,
        "subscription_price": 9.99,
        "subscriber_count": 10,
        "bio": "I create awesome content!",
        "is_verified": false,
        "subscription_price_id": "price_1234567890"
      },
      "stats": {
        "total_likes": 150,
        "total_views": 1000
      }
    }
    ```

#### Get Creator Accounts
- **GET /users/creator-accounts/**
  - Description: Retrieves a list of all creator accounts.
  - Authentication: Not required
  - Response:
    ```json
    {
      "count": 2,
      "next": null,
      "previous": null,
      "results": [
        {
          "user": 1,
          "subscription_price": 9.99,
          "subscriber_count": 10,
          "bio": "I create awesome content!",
          "is_verified": false,
          "subscription_price_id": "price_1234567890"
        },
        {
          "user": 2,
          "subscription_price": 4.99,
          "subscriber_count": 5,
          "bio": "New creator here!",
          "is_verified": false,
          "subscription_price_id": "price_0987654321"
        }
      ]
    }
    ```

#### Create Spectator Account
- **POST /users/create-spectator-account/**
  - Description: Creates a spectator account.
  - Authentication: Not required
  - Request:
    ```json
    {
      "user": 1
    }
    ```
  - Response:
    ```json
    {
      "message": "Spectator account created successfully",
      "data": {
        "user": 1,
        "stripe_customer_id": null
      }
    }
    ```

#### Spectator Account Detail
- **GET /users/spectator-account/**
  - Description: Retrieves details of the authenticated user's spectator account.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "data": {
        "user": 1,
        "subscriptions": [1, 2],
        "liked_visions": [1, 3, 5],
        "watch_later": [2, 4],
        "liked_comments": [1, 7, 9],
        "watch_history": [1, 2, 3, 4, 5],
        "interests": [
          {
            "id": 1,
            "name": "Technology"
          },
          {
            "id": 2,
            "name": "Sports"
          }
        ],
        "stripe_customer_id": "cus_1234567890"
      }
    }
    ```

#### Get Spectator Accounts
- **GET /users/spectator-accounts/**
  - Description: Retrieves a list of all spectator accounts.
  - Authentication: Not required
  - Response:
    ```json
    [
      {
        "user": 1,
        "subscriptions": [1, 2],
        "liked_visions": [1, 3, 5],
        "watch_later": [2, 4],
        "liked_comments": [1, 7, 9],
        "watch_history": [1, 2, 3, 4, 5],
        "interests": [1, 2],
        "stripe_customer_id": "cus_1234567890"
      },
      {
        "user": 2,
        "subscriptions": [3],
        "liked_visions": [2, 4],
        "watch_later": [1, 3],
        "liked_comments": [2, 8],
        "watch_history": [1, 2, 3],
        "interests": [2, 3],
        "stripe_customer_id": "cus_0987654321"
      }
    ]
    ```

#### Get Popular Creators
- **GET /users/popular-creators/**
  - Description: Retrieves a list of popular creators based on views, likes, and subscribers.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "count": 2,
      "next": null,
      "previous": null,
      "results": [
        {
          "user": 1,
          "subscription_price": 9.99,
          "subscriber_count": 100,
          "bio": "Top creator here!",
          "is_verified": true,
          "subscription_price_id": "price_1234567890",
          "weighted_score": 1500
        },
        {
          "user": 2,
          "subscription_price": 4.99,
          "subscriber_count": 50,
          "bio": "Rising star creator!",
          "is_verified": false,
          "subscription_price_id": "price_0987654321",
          "weighted_score": 1000
        }
      ]
    }
    ```

#### Send Sign-in Code
- **POST /users/auth/send-signin-code/**
  - Description: Sends a sign-in code for authentication.
  - Authentication: Not required
  - Request:
    ```json
    {
      "code": "12345"
    }
    ```
  - Response:
    ```json
    {
      "message": "success"
    }
    ```

#### Check Sign-in Status
- **GET /users/auth/check-signin-status/**
  - Description: Checks the status of a sign-in attempt.
  - Authentication: Not required
  - Query Parameters: code
  - Response:
    ```json
    {
      "status": "success",
      "user_id": 1,
      "username": "johndoe",
      "auth_token": "abcdef1234567890"
    }
    ```

#### Register User
- **POST /users/register/**
  - Description: Registers a new user.
  - Authentication: Not required
  - Request:
    ```json
    {
      "username": "johndoe",
      "email": "johndoe@example.com",
      "firstname": "John",
      "lastname": "Doe",
      "password": "securepassword123"
    }
    ```
  - Response:
    ```json
    {
      "user_id": 1,
      "username": "johndoe",
      "token": "abcdef1234567890"
    }
    ```

#### Sign In
- **POST /users/sign-in/**
  - Description: Authenticates a user and returns a token.
  - Authentication: Not required
  - Request:
    ```json
    {
      "username": "johndoe",
      "password": "securepassword123"
    }
    ```
  - Response:
    ```json
    {
      "user_id": 1,
      "username": "johndoe",
      "token": "abcdef1234567890"
    }
    ```

#### Sign In with Google
- **POST /users/sign-in-google/**
  - Description: Authenticates a user using Google credentials.
  - Authentication: Not required
  - Request:
    ```json
    {
      "credential": "google_id_token"
    }
    ```
  - Response:
    ```json
    {
      "user_id": 1,
      "username": "johndoe",
      "email": "johndoe@example.com",
      "token": "abcdef1234567890"
    }
    ```

#### Sign In with Facebook
- **POST /users/sign-in-facebook/**
  - Description: Authenticates a user using Facebook credentials.
  - Authentication: Not required
  - Request:
    ```json
    {
      "access_token": "facebook_access_token"
    }
    ```
  - Response:
    ```json
    {
      "user_id": 1,
      "username": "johndoe",
      "email": "johndoe@example.com",
      "token": "abcdef1234567890"
    }
    ```

#### Sign In with Apple
- **POST /users/sign-in-apple/**
  - Description: Authenticates a user using Apple credentials.
  - Authentication: Not required
  - Request:
    ```json
    {
      "access_token": "apple_id_token",
      "refresh_token": "apple_refresh_token"
    }
    ```
  - Response:
    ```json
    {
      "user_id": 1,
      "username": "johndoe",
      "email": "johndoe@example.com",
      "token": "abcdef1234567890",
      "refresh_token": "apple_refresh_token"
    }
    ```

#### Update User Details
- **PUT /users/update-user-details/**
  - Description: Updates the authenticated user's details.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "username": "newusername",
      "first_name": "John",
      "last_name": "Doe"
    }
    ```
  - Response:
    ```json
    {
      "id": 1,
      "username": "newusername",
      "email": "johndoe@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "profile_picture_url": "https://example.com/profile.jpg",
      "cover_picture_url": "https://example.com/cover.jpg",
      "is_spectator": true,
      "is_creator": false,
      "sign_in_method": "email"
    }
    ```

#### Creator Live Status
- **GET /users/creator-live-status/<int:creator_id>/**
  - Description: Checks if a creator is currently live streaming.
  - Authentication: Not required
  - Path Parameters: creator_id
  - Response:
    ```json
    {
      "is_live": true,
      "creator_id": 1,
      "vision": {
        "id": 5,
        "title": "Live Stream Title",
        "description": "Live Stream Description",
        "start_time": "2023-05-01T15:30:00Z"
      }
    }
    ```

#### Search Creators
- **POST /users/creators/search/**
  - Description: Searches for creators based on username, bio, and interests.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "search_text": "tech",
      "interest": "Technology"
    }
    ```
  - Response:
    ```json
    {
      "count": 2,
      "next": null,
      "previous": null,
      "results": [
        {
          "user": {
            "id": 1,
            "username": "techguru",
            "first_name": "Tech",
            "last_name": "Guru",
            "profile_picture_url": "https://example.com/techguru.jpg",
            "cover_picture_url": "https://example.com/techguru_cover.jpg",
            "is_spectator": false,
            "is_creator": true,
            "sign_in_method": "email"
          },
          "subscription_price": 9.99,
          "subscriber_count": 100,
          "bio": "I love talking about technology",
          "is_verified": true,
          "subscription_price_id": "price_1234567890"
        },
        {
          "user": {
            "id": 2,
            "username": "techenthusiast",
            "first_name": "Tech",
            "last_name": "Enthusiast",
            "profile_picture_url": "https://example.com/techenthusiast.jpg",
            "cover_picture_url": "https://example.com/techenthusiast_cover.jpg",
            "is_spectator": false,
            "is_creator": true,
            "sign_in_method": "google"
          },
          "subscription_price": 4.99,
          "subscriber_count": 50,
          "bio": "Passionate about all things tech",
          "is_verified": false,
          "subscription_price_id": "price_0987654321"
        }
      ]
    }
    ```

### Visions Endpoints

#### Create Vision
- **POST /visions/create-vision/**
  - Description: Creates a new vision.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "title": "My New Vision",
      "description": "This is a description of my vision",
      "interests": ["Technology", "Art"],
      "aspect_ratio": "16:9",
      "stereo_mapping": "normal"
    }
    ```
  - Response:
    ```json
    {
      "data": {
        "url": "https://s3-bucket-url/filename.mp4",
        "fields": {
          // S3 presigned post fields
        }
      },
      "url": "https://s3-bucket-url/filename.mp4",
      "id": 1
    }
    ```

#### Create Live Vision
- **POST /visions/create-live-vision/**
  - Description: Creates a new live vision.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "title": "My Live Stream",
      "description": "This is a live stream",
      "interests": ["Technology", "Gaming"]
    }
    ```
  - Response:
    ```json
    {
      "message": "Successfully created live vision",
      "vision_id": 1,
      "hls_url": "https://example.com/1.m3u8",
      "rtmp_stream_link": "rtmp://example.com/stream/1"
    }
    ```

#### Upload Thumbnail
- **POST /visions/upload-thumbnail/<int:vision_pk>/**
  - Description: Uploads a thumbnail for a specific vision.
  - Authentication: Required (Token Authentication)
  - Request: Multipart form data with 'thumbnail' file
  - Response:
    ```json
    {
      "message": "Successfully uploaded thumbnail"
    }
    ```

#### Update or Get Vision Info
- **GET /visions/vision-info/<int:vision_pk>/**
  - Description: Retrieves information about a specific vision.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Successfully retrieved vision",
      "data": {
        "id": 1,
        "title": "Vision Title",
        "thumbnail": "https://example.com/thumbnail.jpg",
        "creator": 1,
        "views": 100,
        "url": "https://example.com/vision.mp4",
        "likes": 50,
        "interests": [1, 2],
        "description": "Vision description",
        "live": false,
        "aspect_ratio": "16:9",
        "stereo_mapping": "normal",
        "created_at": "2023-05-01T12:00:00Z",
        "is_highlight": false,
        "is_saved": false,
        "private_user": null
      }
    }
    ```

- **PUT /visions/vision-info/<int:vision_pk>/**
  - Description: Updates information about a specific vision.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "title": "Updated Vision Title",
      "description": "Updated description",
      "interests": [1, 3],
      "is_highlight": true
    }
    ```
  - Response:
    ```json
    {
      "message": "Successfully updated vision",
      "data": {
        // Updated vision data
      }
    }
    ```

#### Get Recommended Visions
- **GET /visions/recommended-visions/**
  - Description: Retrieves a list of recommended visions for the user.
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of vision objects

#### Get Visions by Creator
- **GET /visions/visions-by-creator/<int:pk>/**
  - Description: Retrieves visions created by a specific creator.
  - Authentication: Not required
  - Response: Paginated list of vision objects

#### Get Visions by Interest
- **POST /visions/visions-by-interest/**
  - Description: Retrieves visions based on specified interests.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "interests": ["Technology", "Art"]
    }
    ```
  - Response: Paginated list of vision objects

#### Like or Dislike Vision
- **POST /visions/like-dislike-vision/<int:pk>/**
  - Description: Likes or dislikes a specific vision.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Vision liked" // or "Vision disliked"
    }
    ```

#### Get Subscription Visions
- **GET /visions/subscriptions/**
  - Description: Retrieves visions from creators the user is subscribed to.
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of vision objects

#### Get Trending Visions
- **GET /visions/trending/**
  - Description: Retrieves trending visions.
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of vision objects

#### Add to Watch History
- **POST /visions/watch-history/add/**
  - Description: Adds a vision to the user's watch history.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "vision_id": 1
    }
    ```
  - Response:
    ```json
    {
      "message": "Added to watch history"
    }
    ```

#### Get Visions by Creator Category
- **GET /visions/visions-by-creator/<int:pk>/<str:category>/**
  - Description: Retrieves visions by a creator in a specific category (saved, highlights, forme).
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of vision objects

#### End Live Vision
- **PUT /visions/end-live-vision/**
  - Description: Ends a live vision stream.
  - Authentication: API Key required
  - Query Parameters: api_key, vision_pk
  - Response:
    ```json
    {
      "message": "Successfully ended live vision"
    }
    ```

#### Like Comment
- **POST /visions/comments/<int:comment_pk>/like/**
  - Description: Likes a specific comment.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Comment liked successfully"
    }
    ```

#### Unlike Comment
- **POST /visions/comments/<int:comment_pk>/unlike/**
  - Description: Unlikes a specific comment.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Comment unliked successfully"
    }
    ```

#### Search Visions
- **POST /visions/search/**
  - Description: Searches for visions based on text and optional interest.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "search_text": "technology",
      "interest": "Science"
    }
    ```
  - Response: Paginated list of vision objects matching the search criteria

#### Get Vision Comments
- **GET /visions/<int:vision_id>/comments/**
  - Description: Retrieves comments for a specific vision.
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of comment objects

#### Get Comment Replies
- **GET /visions/comment-replies/<int:comment_id>/**
  - Description: Retrieves replies to a specific comment.
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of reply objects

### Events Endpoints

#### Get, Create, or Delete Events
- **GET /events/events/**
  - Description: Retrieves all events.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Successfully retrieved events",
      "data": [
        {
          "id": 1,
          "creator": 1,
          "title": "Event Title",
          "description": "Event Description",
          "vision": 1,
          "start_time": "2023-05-01T12:00:00Z",
          "remind_me_list": [1, 2, 3]
        },
        // ... more events
      ]
    }
    ```

- **POST /events/events/**
  - Description: Creates a new event.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "title": "New Event",
      "description": "Event Description",
      "start_time": "2023-05-01T12:00:00Z",
      "interests": [1, 2],
      "thumbnail": <file>
    }
    ```
  - Response:
    ```json
    {
      "message": "Successfully created event",
      "data": {
        "id": 1,
        "creator": 1,
        "title": "New Event",
        "description": "Event Description",
        "vision": 1,
        "start_time": "2023-05-01T12:00:00Z",
        "remind_me_list": []
      },
      "id": 1
    }
    ```

#### Edit or Delete Event
- **PUT /events/edit-delete-event/<int:pk>/**
  - Description: Edits an existing event. (Not implemented in the provided code)
  - Authentication: Required (Token Authentication)

- **DELETE /events/edit-delete-event/<int:pk>/**
  - Description: Deletes a specific event.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Successfully deleted event"
    }
    ```

#### Activate Event Livestream
- **POST /events/activate-event-livestream/<int:pk>/**
  - Description: Activates the livestream for a specific event.
  - Authentication: Not required (but recommended to add)
  - Response:
    ```json
    {
      "message": "Successfully activated event livestream",
      "vision_id": 1,
      "hls_url": "https://example.com/1.m3u8",
      "rtmp_stream_link": "rtmp://example.com/stream/1"
    }
    ```

#### Get Events by Creator
- **GET /events/events-by-creator/<int:pk>/**
  - Description: Retrieves events created by a specific creator.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Successfully retrieved events",
      "data": [
        {
          "id": 1,
          "creator": 1,
          "title": "Event Title",
          "description": "Event Description",
          "vision": 1,
          "start_time": "2023-05-01T12:00:00Z",
          "remind_me_list": [1, 2, 3]
        },
        // ... more events
      ]
    }
    ```

#### Get Upcoming Events by Interests
- **GET /events/upcoming-events-by-interests/**
  - Description: Retrieves upcoming events based on specified interests.
  - Authentication: Required (Token Authentication)
  - Query Parameters: interests (comma-separated list)
  - Response:
    ```json
    {
      "message": "Successfully retrieved events",
      "data": [
        {
          "id": 1,
          "creator": 1,
          "title": "Event Title",
          "description": "Event Description",
          "vision": 1,
          "start_time": "2023-05-01T12:00:00Z",
          "remind_me_list": [1, 2, 3]
        },
        // ... more events
      ]
    }
    ```

#### Add or Remove from Remind Me List
- **POST /events/remind-me/<int:event_pk>/**
  - Description: Adds or removes the authenticated user from an event's remind me list.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Spectator successfully added to remind me list"
    }
    ```
    or
    ```json
    {
      "message": "Spectator successfully removed from remind me list"
    }
    ```

#### Get Events from Subscriptions
- **GET /events/events-from-subscriptions/**
  - Description: Retrieves upcoming events from creators the user is subscribed to.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Successfully retrieved events",
      "data": [
        {
          "id": 1,
          "creator": 1,
          "title": "Event Title",
          "description": "Event Description",
          "vision": 1,
          "start_time": "2023-05-01T12:00:00Z",
          "remind_me_list": [1, 2, 3]
        },
        // ... more events
      ]
    }
    ```

#### Get Recommended Events
- **GET /events/recommended/**
  - Description: Retrieves recommended events based on user interests and subscriptions.
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of event objects

#### Get Upcoming Events
- **GET /events/upcoming/**
  - Description: Retrieves upcoming events based on user interests and subscriptions.
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of event objects

### Subscriptions Endpoints

#### Subscribe to Creator
- **POST /subscriptions/subscribe/<int:pk>/**
  - Description: Subscribes the authenticated user to a specific creator.
  - Authentication: Required (Token Authentication)
  - Path Parameters: pk (creator's id)
  - Response:
    ```json
    {
      "message": "success",
      "type": "payment",
      "client_secret": "pi_1234567890_secret_1234567890",
      "subscription_id": "sub_1234567890"
    }
    ```
  - Possible Errors:
    - 404: Creator not found
    - 400: Creator has no subscription price, Missing payment methods, Already subscribed

#### Get User's Subscriptions
- **GET /subscriptions/subscriptions/**
  - Description: Retrieves all subscriptions for the authenticated user.
  - Authentication: Required (Token Authentication)
  - Response:
    ```json
    {
      "message": "Successfully retrieved subscriptions",
      "data": [
        {
          "id": 1,
          "user": {
            "id": 1,
            "username": "creator1"
          },
          "subscription_price": 9.99,
          "subscriber_count": 100
        },
        // ... more subscriptions
      ]
    }
    ```

#### Update Creator's Subscription Price
- **POST /subscriptions/update-creator-price/**
  - Description: Updates the subscription price for the authenticated creator.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "price": 9.99
    }
    ```
  - Response:
    ```json
    {
      "message": "Subscription price updated successfully",
      "new_price": 9.99,
      "stripe_price_id": "price_1234567890"
    }
    ```

#### Get Subscribed Creators
- **GET /subscriptions/subscribed-creators/**
  - Description: Retrieves a paginated list of creators the authenticated user is subscribed to.
  - Authentication: Required (Token Authentication)
  - Response: Paginated list of creator objects
    ```json
    {
      "count": 10,
      "next": "http://example.com/subscriptions/subscribed-creators/?page=2",
      "previous": null,
      "results": [
        {
          "id": 1,
          "user": {
            "id": 1,
            "username": "creator1"
          },
          "subscription_price": 9.99,
          "subscriber_count": 100
        },
        // ... more creators
      ]
    }
    ```

#### Check Subscription Status
- **GET /subscriptions/subscription-status/<int:creator_id>/**
  - Description: Checks if the authenticated user is subscribed to a specific creator.
  - Authentication: Required (Token Authentication)
  - Path Parameters: creator_id
  - Response:
    ```json
    {
      "is_subscribed": true,
      "creator_id": 1,
      "creator_username": "creator1"
    }
    ```

#### Unsubscribe from Creator
- **POST /subscriptions/unsubscribe/<int:pk>/**
  - Description: Unsubscribes the authenticated user from a specific creator.
  - Authentication: Required (Token Authentication)
  - Path Parameters: pk (creator's id)
  - Response:
    ```json
    {
      "message": "Successfully unsubscribed from creator1",
      "end_date": "2023-06-01T00:00:00Z"
    }
    ```
  - Possible Errors:
    - 404: Spectator or Creator not found
    - 400: Not subscribed

### Payments Endpoints

#### Get Transactions
- **GET /payments/transactions/**
  - Description: Retrieves all transactions for the authenticated user.
  - Authentication: Not explicitly required, but recommended to add
  - Response:
    ```json
    {
      "message": "Successfully retrieved transactions",
      "data": [
        {
          "id": 1,
          "user": 1,
          "amount": 10.00,
          "transaction_type": "PURCHASE",
          "status": "COMPLETED",
          "created_at": "2023-05-01T12:00:00Z"
        },
        // ... more transactions
      ]
    }
    ```
  - Possible Errors:
    - 500: Internal Server Error

#### Create Transaction
- **POST /payments/create-transaction/**
  - Description: Creates a new transaction for the authenticated user.
  - Authentication: Not explicitly required, but recommended to add
  - Request:
    ```json
    {
      "amount": 10.00,
      "transaction_type": "PURCHASE",
      "status": "COMPLETED"
    }
    ```
  - Response:
    ```json
    {
      "message": "Transaction created successfully",
      "data": {
        "id": 1,
        "user": 1,
        "amount": 10.00,
        "transaction_type": "PURCHASE",
        "status": "COMPLETED",
        "created_at": "2023-05-01T12:00:00Z"
      }
    }
    ```
  - Possible Errors:
    - 400: Bad Request (invalid data)
    - 500: Internal Server Error

#### Send Tip
- **POST /payments/send-tip/**
  - Description: Sends a tip from the authenticated user to a creator.
  - Authentication: Required (Token Authentication)
  - Request:
    ```json
    {
      "amount": 5.00,
      "creator_id": 1,
      "comment_text": "Great content!"
    }
    ```
  - Response:
    ```json
    {
      "status": "success",
      "tip": {
        "id": 1,
        "amount": 5.00,
        "message": "Great content!",
        "user": 1,
        "creator": 1,
        "comment": 1
      }
    }
    ```
  - Possible Errors:
    - 400: Bad Request (missing payment method, Stripe error)
    - 404: Not Found (creator not found)
    - 500: Internal Server Error

## View Bot Prevention

The system now includes advanced protections against view bots:

1. **View Duration Tracking**: Views must be at least 10 seconds to count
2. **Rate Limiting**: Users are limited to 10 views per 5 minutes
3. **IP Tracking**: IP addresses are stored with views to detect patterns
4. **Suspicious Activity Detection**: Algorithm identifies bot-like behavior
5. **Individual View Recording**: Each view is stored separately in the ViewCount model
6. **Valid/Invalid Flagging**: Views are flagged as valid or invalid based on bot detection
7. **Scheduled Cleanup**: Run the cleanup task to adjust view counts periodically

### View Tracking Architecture

The system uses two models to track views:

1. **WatchHistory**: Tracks which videos a user has watched for user history UI purposes (unique per user/video combination)
2. **ViewCount**: Records every individual view with metadata for bot detection and accurate counting

This dual approach allows:
- Showing users which videos they've watched (WatchHistory)
- Accurately counting all legitimate views (ViewCount)
- Detecting and filtering out bot-generated views

### Setting up scheduled cleanup

To schedule the suspicious view cleanup task to run daily, add it to your cron tasks:

```bash
# Edit crontab
crontab -e

# Add this line to run cleanup at 3 AM every day
0 3 * * * cd /path/to/project && python manage.py cleanup_suspicious_views >> /path/to/logs/cleanup.log 2>&1
```

Run the cleanup task manually in dry-run mode to see potential changes without making updates:

```bash
python manage.py cleanup_suspicious_views --dry-run
```
