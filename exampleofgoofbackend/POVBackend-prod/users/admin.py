from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import SignInCodeRequest, User, Interest, Spectator, Creator, Report, WatchHistory

admin.site.register(User, UserAdmin)
admin.site.register(Interest)
admin.site.register(Spectator)
admin.site.register(Creator)
admin.site.register(SignInCodeRequest)
admin.site.register(Report)
admin.site.register(WatchHistory)
