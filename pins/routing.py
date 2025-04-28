from django.urls import re_path
from .consumers import PinConsumer

websocket_urlpatterns = [
    re_path(r'ws/pins/$', PinConsumer.as_asgi()),
] 