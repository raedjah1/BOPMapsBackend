from django.shortcuts import render
from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Friend
from .serializers import FriendSerializer, FriendRequestSerializer
from bopmaps.views import BaseModelViewSet
import logging

logger = logging.getLogger('bopmaps')


class FriendViewSet(BaseModelViewSet):
    """
    API viewset for Friend management.
    """
    serializer_class = FriendSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Return all accepted friendships for the current user
        """
        return Friend.objects.filter(
            (Q(requester=self.request.user) | Q(recipient=self.request.user)),
            status='accepted'
        )
    
    @action(detail=False, methods=['GET'])
    def all_friends(self, request):
        """
        Get a list of all the current user's friends
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['POST'])
    def unfriend(self, request, pk=None):
        """
        Remove a friendship
        """
        try:
            friendship = self.get_object()
            
            if friendship.requester != request.user and friendship.recipient != request.user:
                return Response(
                    {"error": "Cannot unfriend a relationship you are not part of"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            friendship.delete()
            return Response({"message": "Friend removed successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error unfriending: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class FriendRequestViewSet(BaseModelViewSet):
    """
    API viewset for FriendRequest management.
    """
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Return all friend requests for the current user
        """
        # By default, show requests sent to or by the current user
        return Friend.objects.filter(
            Q(requester=self.request.user) | Q(recipient=self.request.user)
        )
    
    def perform_create(self, serializer):
        """
        Set the requester to the current user when creating a friend request
        """
        serializer.save(requester=self.request.user, status='pending')
    
    @action(detail=False, methods=['GET'])
    def sent(self, request):
        """
        Get friend requests sent by the current user
        """
        queryset = Friend.objects.filter(requester=request.user, status='pending')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['GET'])
    def received(self, request):
        """
        Get friend requests received by the current user
        """
        queryset = Friend.objects.filter(recipient=request.user, status='pending')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['POST'])
    def accept(self, request, pk=None):
        """
        Accept a friend request
        """
        try:
            friend_request = self.get_object()
            
            if friend_request.recipient != request.user:
                return Response(
                    {"error": "Cannot accept a friend request that was not sent to you"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if friend_request.status != 'pending':
                return Response(
                    {"error": "This friend request has already been processed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                friend_request.status = 'accepted'
                friend_request.save()
                
                serializer = self.get_serializer(friend_request)
                return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error accepting friend request: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['POST'])
    def reject(self, request, pk=None):
        """
        Reject a friend request
        """
        try:
            friend_request = self.get_object()
            
            if friend_request.recipient != request.user:
                return Response(
                    {"error": "Cannot reject a friend request that was not sent to you"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if friend_request.status != 'pending':
                return Response(
                    {"error": "This friend request has already been processed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                friend_request.status = 'rejected'
                friend_request.save()
                
                serializer = self.get_serializer(friend_request)
                return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error rejecting friend request: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['POST'])
    def cancel(self, request, pk=None):
        """
        Cancel a friend request you've sent
        """
        try:
            friend_request = self.get_object()
            
            if friend_request.requester != request.user:
                return Response(
                    {"error": "Cannot cancel a friend request that you didn't send"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if friend_request.status != 'pending':
                return Response(
                    {"error": "This friend request has already been processed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            friend_request.delete()
            return Response({"message": "Friend request cancelled"}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error cancelling friend request: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
