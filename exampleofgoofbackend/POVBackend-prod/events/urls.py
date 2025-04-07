from django.urls import path
from .views import get_create_delete_events, edit_or_delete_events, activate_event_livestream, get_event_by_creator, get_recommended_events, get_trending_events_view, get_upcoming_events, get_upcoming_events_by_interests, add_or_remove_from_remind_me_list, get_events_from_subscriptions, get_creator_events_by_day, get_creator_events_by_month, get_events_starting_next_hour

urlpatterns = [
    path('events/', get_create_delete_events, name='get_create_delete_events'),
    path('edit-delete-event/<int:pk>/', edit_or_delete_events, name='edit_or_delete_events'),
    path('activate-event-livestream/<int:pk>/', activate_event_livestream, name='activate_event_livestream'),
    path('events-by-creator/<int:pk>/', get_event_by_creator, name='get_event_by_creator'),
    path('upcoming-events-by-interests/', get_upcoming_events_by_interests, name='get_upcoming_events_by_interests'),
    path('remind-me/<int:event_pk>/', add_or_remove_from_remind_me_list, name='add_or_remove_from_remind_me_list'),
    path('events-from-subscriptions/', get_events_from_subscriptions, name='get_events_from_subscriptions'),
    path('recommended-events/', get_recommended_events, name='get_recommended_events'),
    path('upcoming/', get_trending_events_view, name='get_trending_events'),
    path('events-by-creator/<int:creator_pk>/day/<str:date>/', get_creator_events_by_day, name='get_creator_events_by_day'),
    path('events-by-creator/<int:creator_pk>/month/<int:year>/<int:month>/', get_creator_events_by_month, name='get_creator_events_by_month'),
    path('next-hour/', get_events_starting_next_hour, name='get_events_starting_next_hour'),
]
