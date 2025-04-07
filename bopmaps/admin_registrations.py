from django.contrib import admin
from django.utils import timezone
from .admin import bopmaps_admin_site
from users.models import User
from pins.models import Pin, PinInteraction
from friends.models import Friend
from music.models import MusicService, Genre, RecentTrack
from gamification.models import Achievement, PinSkin, UserAchievement
from geo.models import TrendingArea, UserLocation

# Register Users models
@admin.register(User, site=bopmaps_admin_site)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'date_joined', 'is_staff')
    search_fields = ('username', 'email')
    list_filter = ('is_active', 'is_staff', 'date_joined')

# Register Pins models
@admin.register(Pin, site=bopmaps_admin_site)
class PinAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'created_at', 'is_private')
    search_fields = ('title', 'description')
    list_filter = ('is_private', 'created_at')

@admin.register(PinInteraction, site=bopmaps_admin_site)
class PinInteractionAdmin(admin.ModelAdmin):
    list_display = ('user', 'pin', 'interaction_type', 'created_at')
    list_filter = ('interaction_type', 'created_at')

# Register Friends models
@admin.register(Friend, site=bopmaps_admin_site)
class FriendAdmin(admin.ModelAdmin):
    list_display = ('requester', 'recipient', 'status', 'created_at')
    list_filter = ('status', 'created_at')

# Register Music models
@admin.register(MusicService, site=bopmaps_admin_site)
class MusicServiceAdmin(admin.ModelAdmin):
    list_display = ('user', 'service_type', 'is_connected')
    list_filter = ('service_type',)
    
    def is_connected(self, obj):
        return obj.expires_at is not None and obj.expires_at > timezone.now()
    is_connected.boolean = True

@admin.register(Genre, site=bopmaps_admin_site)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(RecentTrack, site=bopmaps_admin_site)
class RecentTrackAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'artist', 'played_at')
    search_fields = ('title', 'artist')
    list_filter = ('played_at',)

# Register Gamification models
@admin.register(Achievement, site=bopmaps_admin_site)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')

@admin.register(PinSkin, site=bopmaps_admin_site)
class PinSkinAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_premium')
    list_filter = ('is_premium',)

@admin.register(UserAchievement, site=bopmaps_admin_site)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ('user', 'achievement', 'completed_at')
    list_filter = ('completed_at',)

# Register Geo models
@admin.register(TrendingArea, site=bopmaps_admin_site)
class TrendingAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'last_updated')
    search_fields = ('name',)

@admin.register(UserLocation, site=bopmaps_admin_site)
class UserLocationAdmin(admin.ModelAdmin):
    list_display = ('user', 'timestamp')
    list_filter = ('timestamp',) 