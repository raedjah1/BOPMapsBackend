from django.contrib import admin

from django.contrib import admin
from .models import StoryNode, StoryOption, Vision, Comment, VisionRequest, AnnoyIndex, VisionSimilarity

admin.site.register(Vision)
admin.site.register(Comment)
admin.site.register(StoryNode)
admin.site.register(StoryOption)
admin.site.register(VisionRequest)
admin.site.register(AnnoyIndex)
admin.site.register(VisionSimilarity)

# Register your models here.
