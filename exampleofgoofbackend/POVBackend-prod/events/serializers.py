from rest_framework import serializers
from .models import Event, Spectator
from videos.serializers import VisionSerializer
from users.serializers import CreatorSerializer

class EventSerializer(serializers.ModelSerializer):
    vision = VisionSerializer(required=False)
    creator = CreatorSerializer(required=False)
    is_subscribed_creator = serializers.BooleanField(read_only=True)
    is_reminded = serializers.SerializerMethodField()
    remind_me_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ['pk', 'creator', 'title', 'description', 'vision', 'start_time', 
                  'is_subscribed_creator', 'is_reminded', 'thumbnail', 'remind_me_count']
        read_only_fields = ['creator', 'vision']

    def get_is_reminded(self, obj):
        user = self.context.get('user')
        if user and user.is_authenticated:
            return obj.remind_me_list.filter(pk=user.pk).exists()
        return False

    def get_remind_me_count(self, obj):
        return obj.remind_me_list.count()