import json
import logging
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.authtoken.models import Token
from rest_framework import status
from http import HTTPStatus
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate
from django.db.models import Sum
from videos.models import Vision
from .models import SignInCodeRequest, User, Spectator, Creator
from .serializers import CreatorSerializer, SpectatorSerializer
from django.db import IntegrityError
import os
import jwt
import requests
from django.utils import timezone
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import timedelta
from rest_framework.authentication import TokenAuthentication
import stripe
from django.conf import settings

logger = logging.getLogger(__name__)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_creator_account(request):
    """
    Create a new creator account for the authenticated user with Stripe Connect integration.
    Creates Stripe Connect account regardless of onboarding completion.

    Args:
        request (Request): The incoming HTTP request containing creator data.

    Returns:
        Response: 
            - 201 CREATED with success message, creator data and Stripe Connect onboarding URL if valid.
            - 400 BAD REQUEST with errors if invalid.
            - 500 INTERNAL SERVER ERROR for unexpected errors.
    """
    try:
        creator_serializer = CreatorSerializer(data=request.data)
        user = request.user

        if creator_serializer.is_valid():
            # Create Stripe Connect account
            try:
                account = stripe.Account.create(
                    type='express',
                    country='US',  # You might want to make this configurable
                    email=user.email,
                    capabilities={
                        'card_payments': {'requested': True},
                        'transfers': {'requested': True},
                    },
                )

                # Create account link for onboarding
                account_link = stripe.AccountLink.create(
                    account=account.id,
                    refresh_url=f'{settings.FRONTEND_URL}/creator/connect/refresh',
                    return_url=f'{settings.FRONTEND_URL}/creator/connect/return',
                    type='account_onboarding',
                )

                # Create creator with Stripe Connect ID
                creator = Creator.objects.create(
                    user=user,
                    subscription_price=request.data.get('subscription_price', 0),
                    subscriber_count=0,
                    stripe_connect_id=account.id,
                    stripe_connect_onboarding_completed=False  # Initially set to False
                )
                creator_account = CreatorSerializer(creator)

                return Response(
                    {
                        "message": "Creator account created successfully",
                        "data": creator_account.data,
                        "stripe_connect_url": account_link.url,
                        "needs_onboarding": True
                    },
                    status=status.HTTP_201_CREATED
                )

            except stripe.error.StripeError as e:
                logger.error(f"Stripe error during creator account creation: {str(e)}")
                return Response(
                    {"error": f"Stripe error: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        else:
            logger.error(f"Creator serialization failed: {creator_serializer.errors}")
            return Response(creator_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except User.DoesNotExist:
        logger.exception(f"User with id {request.user.pk} does not exist.")
        return Response(
            {"error": "User does not exist"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception("Unexpected error during creator account creation.")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def creator_account_detail(request):
    """
    Retrieve or delete the creator account of the authenticated user.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        Response:
            - GET:
                - 200 OK with creator data and statistics.
                - 404 NOT FOUND if creator account does not exist.
            - DELETE:
                - 200 OK with success message upon deletion.
                - 400 BAD REQUEST or 500 INTERNAL SERVER ERROR if deletion fails.
    """
    user = request.user
    if request.method == 'GET':
        try:
            creator_account = Creator.objects.select_related('user').get(user=user)
            creator_account_serializer = CreatorSerializer(creator_account)
            visions = Vision.with_locks.with_is_locked(user).filter(creator=creator_account)
            total_likes = visions.aggregate(total_likes=Sum('likes'))['total_likes'] or 0
            total_views = visions.aggregate(total_views=Sum('views'))['total_views'] or 0
            return Response(
                {
                    "data": creator_account_serializer.data,
                    "stats": {
                        "total_likes": total_likes,
                        "total_views": total_views
                    }
                },
                status=HTTPStatus.OK
            )
        except Creator.DoesNotExist:
            logger.warning(f"Creator account for user id {user.pk} not found.")
            return Response(
                {"error": True, "message": f"The user with id {user.pk} has no creator account"},
                status=HTTPStatus.NOT_FOUND
            )
        except Exception as e:
            logger.exception("Error retrieving creator account details.")
            return Response(
                {"error": True, "message": str(e)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR
            )
    elif request.method == 'DELETE':
        try:
            deleted_count, _ = Creator.objects.filter(user=user).delete()
            if deleted_count:
                return Response(
                    {"message": f"Successfully deleted creator account for user with id {user.pk}"},
                    status=HTTPStatus.OK
                )
            else:
                return Response(
                    {"error": True, "message": f"No creator account found for user with id {user.pk}"},
                    status=HTTPStatus.NOT_FOUND
                )
        except Exception as e:
            logger.exception("Error deleting creator account.")
            return Response(
                {"error": True, "message": f"There was an error deleting creator account for user with id {user.pk}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR
            )

@api_view(['GET'])
@permission_classes([AllowAny])
def get_creator_accounts(request):
    """
    Retrieve a paginated list of all creator accounts.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        Response:
            - 200 OK with serialized creator accounts.
    """
    try:
        accounts = Creator.objects.select_related('user').all()
        paginator = PageNumberPagination()
        paginator.page_size = 10
        result_page = paginator.paginate_queryset(accounts, request)
        serialized_accounts = CreatorSerializer(result_page, many=True).data
        return paginator.get_paginated_response(serialized_accounts)
    except Exception as e:
        logger.exception("Error retrieving creator accounts.")
        return Response(
            {"error": "Failed to retrieve creator accounts."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_spectator_account(request):
    """
    Create a new spectator account for the authenticated user.

    Args:
        request (Request): The incoming HTTP request containing spectator data.

    Returns:
        Response:
            - 201 CREATED with success message and spectator data if valid.
            - 400 BAD REQUEST with errors if invalid.
    """
    try:
        spectator_serializer = SpectatorSerializer(data=request.data)
        user = request.user

        if spectator_serializer.is_valid():
            spectator = spectator_serializer.save(user=user)
            return Response(
                {"message": "Spectator account created successfully", "data": SpectatorSerializer(spectator).data},
                status=status.HTTP_201_CREATED
            )
        else:
            logger.error(f"Spectator serialization failed: {spectator_serializer.errors}")
            return Response(spectator_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error during spectator account creation.")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def spectator_account_detail(request):
    """
    Retrieve or delete the spectator account of the authenticated user.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        Response:
            - GET:
                - 200 OK with spectator data.
                - 404 NOT FOUND if spectator account does not exist.
            - DELETE:
                - 200 OK with success message upon deletion.
                - 400 BAD REQUEST if deletion fails.
    """
    user = request.user
    if request.method == 'GET':
        try:
            spectator_account = Spectator.objects.select_related('user').get(user=user)
            spectator_account_serializer = SpectatorSerializer(spectator_account)
            return Response({"data": spectator_account_serializer.data}, status=HTTPStatus.OK)
        except Spectator.DoesNotExist:
            logger.warning(f"Spectator account for user id {user.pk} not found.")
            return Response(
                {"message": f"User with id {user.pk} does not have a spectator account"},
                status=HTTPStatus.NOT_FOUND
            )
        except Exception as e:
            logger.exception("Error retrieving spectator account details.")
            return Response(
                {"error": True, "message": str(e)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR
            )
    elif request.method == 'DELETE':
        try:
            deleted_count, _ = Spectator.objects.filter(user=user).delete()
            if deleted_count:
                return Response(
                    {"message": f"Successfully deleted spectator account for user with id {user.pk}"},
                    status=HTTPStatus.OK
                )
            else:
                return Response(
                    {"message": f"No spectator account found for user with id {user.pk}"},
                    status=HTTPStatus.NOT_FOUND
                )
        except Exception as e:
            logger.exception("Error deleting spectator account.")
            return Response(
                {"message": f"There was an error deleting spectator account of user with id {user.pk}"},
                status=HTTPStatus.BAD_REQUEST
            )

@api_view(['GET'])
@permission_classes([AllowAny])
def get_spectator_accounts(request):
    """
    Retrieve a list of all spectator accounts.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        Response:
            - 200 OK with serialized spectator accounts.
    """
    try:
        accounts = Spectator.objects.select_related('user').all()
        serialized_accounts = SpectatorSerializer(accounts, many=True).data
        return Response(serialized_accounts, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("Error retrieving spectator accounts.")
        return Response(
            {"error": "Failed to retrieve spectator accounts."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    """
    Register a new user with the provided details.

    Args:
        request (Request): The incoming HTTP request containing user registration data.

    Returns:
        Response:
            - 201 CREATED with user details and token upon successful registration.
            - 400 BAD REQUEST with error messages if validation fails.
            - 500 INTERNAL SERVER ERROR for unexpected errors.
    """
    try:
        email = request.data.get('email')
        first_name = request.data.get('firstname')
        last_name = request.data.get('lastname')
        password = request.data.get('password')
        password_confirmation = request.data.get('password_confirmation')

        logger.debug(f"Registering user with email: {email}, first_name: {first_name}, last_name: {last_name}")

        # Validate required fields
        if not all([email, first_name, last_name, password, password_confirmation]):
            logger.warning("Registration failed: Missing required fields.")
            return Response({'error': 'All fields are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate password confirmation
        if password != password_confirmation:
            logger.warning("Registration failed: Passwords do not match.")
            return Response({'error': 'Passwords do not match'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate unique email
        if User.objects.filter(email=email).exists():
            logger.warning(f"Registration failed: Email {email} already in use.")
            return Response({'error': 'Email address already in use'}, status=status.HTTP_400_BAD_REQUEST)

        # Create user
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password
        )

        # Create associated spectator and creator accounts
        Spectator.objects.create(user=user)
        Creator.objects.create(user=user)

        # Generate auth token
        token, _ = Token.objects.get_or_create(user=user)

        logger.info(f"User registered successfully with id {user.id}.")

        return Response(
            {
                'user_id': user.id,
                'profile_picture_url': user.profile_picture_url,
                'cover_picture_url': user.cover_picture_url,
                'is_spectator': user.is_spectator,
                'is_creator': user.is_creator,
                'sign_in_method': user.sign_in_method,
                'token': token.key
            },
            status=status.HTTP_201_CREATED
        )
    except IntegrityError:
        logger.exception("Registration failed: Integrity error.")
        return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error during user registration.")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def sign_in(request):
    """
    Authenticate a user with username/email and password.

    Args:
        request (Request): The incoming HTTP request containing authentication credentials.

    Returns:
        Response:
            - 200 OK with user details and token if authentication is successful.
            - 400 BAD REQUEST with error message if credentials are invalid.
    """
    try:
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            logger.warning("Sign-in failed: Username and password are required.")
            return Response({'error': 'Username and password are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Allow sign-in with email
        if '@' in username:
            try:
                user_obj = User.objects.get(email=username)
                username = user_obj.username
            except User.DoesNotExist:
                logger.warning(f"Sign-in failed: Invalid email {username}.")
                return Response({'error': 'Invalid email'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)

        # Get fresh user instance from database to ensure all fields are up to date
        if user:
            user = User.objects.get(pk=user.pk)


        if user:
            token, _ = Token.objects.get_or_create(user=user)
            response_data = {
                'user_id': user.pk,
                'username': user.username,
                'token': token.key,
                'profile_picture_url': user.profile_picture_url,
                'cover_picture_url': user.cover_picture_url,
                'is_spectator': user.is_spectator,
                'is_creator': user.is_creator,
                'sign_in_method': user.sign_in_method
            }
            logger.info(f"User {user.username} signed in successfully.")
            return Response(response_data, status=status.HTTP_200_OK)

        logger.warning("Sign-in failed: Invalid credentials.")
        return Response({'error': 'Invalid Credentials'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error during sign-in.")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def sign_in_google(request):
    """
    Authenticate or register a user using Google OAuth2 token.

    Args:
        request (Request): The incoming HTTP request containing Google credential.

    Returns:
        Response:
            - 200 OK with user details and token.
            - 403 FORBIDDEN if Google token is invalid.
            - 500 INTERNAL SERVER ERROR for unexpected errors.
    """
    try:
        google_token = request.data.get('credential')
        if not google_token:
            logger.warning("Google sign-in failed: Credential not provided.")
            return Response({"error": "Credential is required"}, status=status.HTTP_400_BAD_REQUEST)

        user_data = id_token.verify_oauth2_token(
            google_token, google_requests.Request(), os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
        )
        email = user_data.get("email")
        if not email:
            logger.warning("Google sign-in failed: Email not found in token.")
            return Response({"error": "Email not found in Google token"}, status=status.HTTP_400_BAD_REQUEST)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": user_data.get("given_name", ""),
                "last_name": user_data.get("family_name", ""),
                "sign_in_method": 'google',
                "password": User.objects.make_random_password()
            }
        )

        Token.objects.get_or_create(user=user)

        Spectator.objects.get_or_create(user=user)
        Creator.objects.get_or_create(user=user)

        if created:
            logger.info(f"New user created via Google sign-in: {user.email}")
            return Response(
                {
                    'user_id': user.id,
                    'token': user.auth_token.key
                },
                status=status.HTTP_201_CREATED
            )
        else:
            logger.info(f"Existing user signed in via Google: {user.email}")
            return Response(
                {
                    'user_id': user.id,
                    'username': user.username,
                    'token': user.auth_token.key
                },
                status=status.HTTP_200_OK
            )
    except ValueError as e:
        logger.error(f"Google token verification failed: {e}")
        return Response({"error": "Invalid Google token"}, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
        logger.exception("Unexpected error during Google sign-in.")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def sign_in_facebook(request):
    """
    Authenticate or register a user using Facebook OAuth data.

    Args:
        request (Request): The incoming HTTP request containing Facebook payload.

    Returns:
        Response:
            - 200 OK with user details and token.
            - 400 BAD REQUEST if email is missing.
            - 500 INTERNAL SERVER ERROR for unexpected errors.
    """
    try:
        payload = request.data
        email = payload.get('email')
        first_name = payload.get('first_name', '')
        last_name = payload.get('last_name', '')
        profile_picture = payload.get('profile_picture', '')

        if not email:
            logger.warning("Facebook sign-in failed: Email is required.")
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": first_name,
                "last_name": last_name,
                "profile_picture_url": profile_picture,
                "sign_in_method": 'facebook',
                "password": User.objects.make_random_password()
            }
        )

        Token.objects.get_or_create(user=user)
        Spectator.objects.get_or_create(user=user)
        Creator.objects.get_or_create(user=user)

        if created:
            logger.info(f"New user created via Facebook sign-in: {user.email}")
            return Response(
                {
                    'user_id': user.id,
                    'token': user.auth_token.key,
                    'profile_picture_url': user.profile_picture_url
                },
                status=status.HTTP_201_CREATED
            )
        else:
            logger.info(f"Existing user signed in via Facebook: {user.email}")
            return Response(
                {
                    'user_id': user.id,
                    'username': user.username,
                    'token': user.auth_token.key,
                    'profile_picture_url': user.profile_picture_url
                },
                status=status.HTTP_200_OK
            )
    except Exception as e:
        logger.exception("Unexpected error during Facebook sign-in.")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def sign_in_apple(request):
    """
    Authenticate or register a user using Apple OAuth2 token.

    Args:
        request (Request): The incoming HTTP request containing Apple access or refresh token.

    Returns:
        Response:
            - 200 OK with user details and token if successful.
            - 403 FORBIDDEN if Apple token is invalid.
            - 500 INTERNAL SERVER ERROR for unexpected errors.
    """
    ACCESS_TOKEN_URL = 'https://appleid.apple.com/auth/token'

    try:
        access_token = request.data.get('access_token')
        refresh_token = request.data.get('refresh_token')

        client_id, client_secret = get_apple_key_and_secret()

        headers = {'Content-Type': "application/x-www-form-urlencoded"}
        data = {
            'client_id': client_id,
            'client_secret': client_secret,
        }

        if refresh_token is None:
            if not access_token:
                logger.warning("Apple sign-in failed: Access token is required.")
                return Response({"error": "Access token is required"}, status=status.HTTP_400_BAD_REQUEST)
            data['code'] = access_token
            data['grant_type'] = 'authorization_code'
        else:
            data['refresh_token'] = refresh_token
            data['grant_type'] = 'refresh_token'

        response = requests.post(ACCESS_TOKEN_URL, data=data, headers=headers)
        response.raise_for_status()
        response_dict = response.json()

        if 'error' not in response_dict:
            id_token_str = response_dict.get('id_token')
            refresh_tk = response_dict.get('refresh_token')

            if id_token_str:
                decoded = jwt.decode(id_token_str, options={"verify_signature": False})
                email = decoded.get('email')

                if email:
                    user, created = User.objects.get_or_create(
                        email=email,
                        defaults={
                            "username": email,
                            "first_name": email.split('@')[0],
                            "last_name": email.split('@')[0],
                            "sign_in_method": 'apple',
                            "password": User.objects.make_random_password()
                        }
                    )

                    Token.objects.get_or_create(user=user)
                    Spectator.objects.get_or_create(user=user)
                    Creator.objects.get_or_create(user=user)

                    response_data = {
                        'user_id': user.id,
                        'username': user.username,
                        'token': user.auth_token.key
                    }

                    if refresh_tk:
                        response_data['refresh_token'] = refresh_tk

                    if created:
                        logger.info(f"New user created via Apple sign-in: {user.email}")
                    else:
                        logger.info(f"Existing user signed in via Apple: {user.email}")

                    return Response(response_data, status=status.HTTP_200_OK)

        logger.warning("Apple sign-in failed: Invalid token.")
        return Response({"error": "Invalid Apple token"}, status=status.HTTP_403_FORBIDDEN)
    except requests.HTTPError as e:
        logger.error(f"HTTP error during Apple sign-in: {e}")
        return Response({"error": "Failed to retrieve token from Apple"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.exception("Unexpected error during Apple sign-in.")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def get_apple_key_and_secret():
    """
    Generate Apple client ID and client secret for OAuth2.

    Returns:
        tuple: (client_id, client_secret)
    """
    AUTH_APPLE_KEY_ID = os.environ.get('AUTH_APPLE_KEY_ID')
    AUTH_APPLE_TEAM_ID = os.environ.get('AUTH_APPLE_TEAM_ID')
    AUTH_APPLE_CLIENT_ID = os.environ.get('AUTH_APPLE_CLIENT_ID')
    AUTH_APPLE_PRIVATE_KEY = os.environ.get('AUTH_APPLE_PRIVATE_KEY')

    headers = {
        'kid': AUTH_APPLE_KEY_ID,
        'alg': 'ES256'
    }
    payload = {
        'iss': AUTH_APPLE_TEAM_ID,
        'iat': int(timezone.now().timestamp()),
        'exp': int((timezone.now() + timedelta(days=180)).timestamp()),
        'aud': 'https://appleid.apple.com',
        'sub': AUTH_APPLE_CLIENT_ID,
    }
    client_secret = jwt.encode(
        payload, AUTH_APPLE_PRIVATE_KEY, algorithm="ES256", headers=headers
    )
    return AUTH_APPLE_CLIENT_ID, client_secret

@api_view(['GET'])
@permission_classes([AllowAny])
def check_signin_status(request):
    """
    Check the sign-in status based on the provided code.

    Args:
        request (Request): The incoming HTTP request containing the sign-in code.

    Returns:
        Response:
            - 200 OK with user details and auth token if sign-in is successful.
            - 200 OK with pending status if sign-in is not yet successful.
            - 404 NOT FOUND if the code is invalid.
            - 400 BAD REQUEST if code is missing.
    """
    code = request.query_params.get('code')
    if not code:
        logger.warning("Check sign-in status failed: Code is required.")
        return Response({'error': 'Code is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        signin_request = SignInCodeRequest.objects.select_related('user').get(code=code)
        if signin_request.status == 'success':
            user = signin_request.user
            token, _ = Token.objects.get_or_create(user=user)

            logger.info(f"Sign-in status checked: success for user {user.username}.")

            return Response(
                {
                    'status': 'success',
                    'user_id': user.pk,
                    'username': user.username,
                    'auth_token': token.key
                },
                status=status.HTTP_200_OK
            )
        else:
            logger.info(f"Sign-in status pending for code {code}.")
            return Response({'status': 'pending'}, status=status.HTTP_200_OK)
    except SignInCodeRequest.DoesNotExist:
        logger.warning(f"Check sign-in status failed: Invalid code {code}.")
        return Response({'error': 'Invalid code'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Unexpected error during sign-in status check.")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def send_signin_code(request):
    """
    Send a sign-in code to the user.

    Args:
        request (Request): The incoming HTTP request containing the sign-in code.

    Returns:
        Response:
            - 200 OK with success message.
            - 400 BAD REQUEST if code is missing.
            - 500 INTERNAL SERVER ERROR for unexpected errors.
    """
    try:
        if hasattr(request, 'data'):
            # DRF request
            code = request.data.get('code')
        else:
            # Regular Django request
            try:
                data = json.loads(request.body)
                code = data.get('code')
            except json.JSONDecodeError:
                code = request.POST.get('code')

        if not code:
            logger.warning("Send sign-in code failed: Code is required.")
            return Response({'error': 'Code is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Create or update the SignInCodeRequest
        signin_request, created = SignInCodeRequest.objects.update_or_create(
            code=code,
            defaults={'status': 'pending'}
        )

        logger.info(f"Sign-in code {'created' if created else 'updated'}: {code}")

        return Response({'message': 'success'}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("Unexpected error while sending sign-in code.")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def verify_vr_code(request):
    """
    Verify the provided VR code for the authenticated user.

    Args:
        request (Request): The incoming HTTP request containing the VR code.

    Returns:
        Response:
            - 200 OK with verification success message.
            - 400 BAD REQUEST with invalid VR code message.
            - 500 INTERNAL SERVER ERROR for unexpected errors.
    """
    code = request.data.get('code')
    if not code:
        logger.warning("Verify VR code failed: Code is required.")
        return Response({'error': 'Code is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        signin_request = SignInCodeRequest.objects.get(code=code, status='pending')
        signin_request.status = 'success'
        signin_request.save()

        logger.info(f"VR code {code} verified successfully for user {request.user.username}.")

        return Response(
            {
                'valid': True,
                'message': 'VR code verified successfully'
            },
            status=status.HTTP_200_OK
        )
    except SignInCodeRequest.DoesNotExist:
        logger.warning(f"Invalid VR code attempted: {code}.")
        return Response(
            {
                'valid': False,
                'message': 'Invalid VR code'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.exception("Unexpected error during VR code verification.")
        return Response(
            {
                'error': True,
                'message': f'Error verifying VR code: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
