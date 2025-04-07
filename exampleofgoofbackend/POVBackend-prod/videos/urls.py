from django.urls import path
from .views import (
    create_highlight, create_live_vision, create_poll, create_vision, delete_comment, delete_vision, dislike_or_undislike_vision, encode, end_live_vision, encoding, get_comment_replies, get_option_upload_url,
    get_poll_details, get_subscription_visions, get_trending_visions, get_vision_comments,
    get_visions_by_creator_category, highlight_complete, like_comment, like_or_unlike_vision, search_visions, submit_poll_vote,
    unlike_comment, upload_complete, upload_thumbnail, update_or_get_vision_info, get_recommended_visions,
    get_visions_by_creator, get_visions_by_interest,
    get_filtered_visions, add_view, create_interactive_story, create_interactive_story_node, get_node_upload_url,
    get_creator_for_me_visions, get_creator_highlights_visions, create_comment, create_comment_reply,
    update_vision_access, get_vision_requests, create_vision_request, respond_to_vision_request, upload_requested_vision,
    get_creator_vision_requests, cancel_vision_request, get_private_visions, get_highlighted_visions, send_request_chat_notification,
    stream_violation, terminate_stream, get_creator_live_visions, purchase_pay_per_view, get_ppv_visions, get_creator_top_povs)

urlpatterns = [
    path('create-vision/', create_vision, name='create_vision'),
    path('create-interactive-story/', create_interactive_story, name='create_interactive_story'),
    path('create-interactive-story-node/', create_interactive_story_node, name='create_interactive_story_node'),
    path('get-node-upload-url/<int:vision_id>/<str:node_id>/', get_node_upload_url, name='get_node_upload_url'),
    path('get-option-upload-url/<int:vision_id>/<str:node_id>/<str:option_id>/', get_option_upload_url, name='get_option_upload_url'),
    path('create-live-vision/', create_live_vision, name='create_live_vision'),
    path('upload-thumbnail/<int:vision_pk>/', upload_thumbnail, name='upload_thumbnail'),
    path('vision-info/<int:vision_pk>/', update_or_get_vision_info, name='update_or_get_vision_info'),
    path('delete-vision/<int:vision_pk>/', delete_vision, name='delete_vision'),
    path('recommended-visions/', get_recommended_visions, name='get_recommended_visions'),
    path('visions-by-creator/<int:pk>/', get_visions_by_creator, name='get_visions_by_creator'),
    path('visions-by-interest/', get_visions_by_interest, name='get_visions_by_interest'),
    path('like-dislike-vision/<int:pk>/', like_or_unlike_vision, name='like_or_dislike_vision'),
    path('like-vision/<int:pk>/', like_or_unlike_vision, name='like_or_unlike_vision'),
    path('dislike-vision/<int:pk>/', dislike_or_undislike_vision, name='dislike_or_undislike_vision'),
    path('subscriptions/', get_subscription_visions, name='get_subscriptions'),
    path('trending/', get_trending_visions, name='get_trending_visions'),
    path('visions-by-creator/<int:pk>/<str:category>/', get_visions_by_creator_category, name='get_visions_by_creator_category'),
    path('creator-live-visions/<int:creator_pk>/', get_creator_live_visions, name='get_creator_live_visions'),
    path('end-live-vision/', end_live_vision, name='end_live_vision'),
    path('comments/<int:comment_pk>/like/', like_comment, name='like_comment'),
    path('comments/<int:comment_pk>/unlike/', unlike_comment, name='unlike_comment'),
    path('comments/<int:comment_pk>/delete/', delete_comment, name='delete_comment'),
    path('search/', search_visions, name='search_visions'),
    path('<int:vision_id>/comments/', get_vision_comments, name='get_vision_comments'),
    path('comment-replies/<int:comment_id>/', get_comment_replies, name='get_comment_replies'),
    path('create-poll/', create_poll, name='create_poll'),
    path('poll-details/<int:poll_id>/', get_poll_details, name='get_poll_details'),
    path('submit-poll-vote/', submit_poll_vote, name='submit_poll_vote'),
    path('encoding-visions/', encoding, name='encoding'),
    path('encode/<int:vision_pk>/', encode, name='encode'),
    path('upload-complete/', upload_complete, name='upload_complete'),
    # path('nearby/', get_nearby_visions, name='get_nearby_visions'),
    path('filtered-visions/<int:creator_id>/', get_filtered_visions, name='get_filtered_visions'),
    path('creator-highlights/<int:creator_pk>/', get_creator_highlights_visions, name='get_creator_highlights_visions'),
    path('creator-for-me/<int:creator_pk>/', get_creator_for_me_visions, name='get_creator_for_me_visions'),
    path('add-view/<int:vision_pk>/', add_view, name='add_view'),
    path('create-comment/<int:vision_id>/', create_comment, name='create_comment'),
    path('create-comment-reply/<int:comment_id>/', create_comment_reply, name='create_comment_reply'),
    path('create-highlight/', create_highlight, name='create-highlight'),
    path('highlight-complete/', highlight_complete, name='highlight-complete'),
    path('vision/<int:vision_pk>/access/', update_vision_access, name='update-vision-access'),
    path('vision-requests/', get_vision_requests, name='get-vision-requests'),
    path('vision-requests/create/', create_vision_request, name='create-vision-request'),
    path('vision-requests/<int:request_id>/respond/', respond_to_vision_request, name='respond-to-vision-request'),
    path('vision-requests/<int:request_id>/upload/', upload_requested_vision, name='upload-requested-vision'),
    path('vision-requests/creator/<int:creator_id>/', get_creator_vision_requests, name='get-creator-vision-requests'),
    path('vision-requests/<int:request_id>/cancel/', cancel_vision_request, name='cancel-vision-request'),
    path('private-visions/<int:creator_pk>/', get_private_visions, name='get-private-visions'),
    path('highlighted-visions/<int:creator_pk>/', get_highlighted_visions, name='get-highlighted-visions'),
    path('vision-requests/<int:request_id>/chat/notify/', send_request_chat_notification, name='send-request-chat-notification'),
    path('stream-violation/', stream_violation, name='stream-violation'),
    path('terminate-stream/', terminate_stream, name='terminate-stream'),
    path('purchase-pay-per-view/<int:vision_pk>/', purchase_pay_per_view, name='purchase-pay-per-view'),
    path('ppv-visions/', get_ppv_visions, name='get-ppv-visions'),
    path('creator-top-povs/<int:creator_pk>/', get_creator_top_povs, name='get-creator-top-povs'),
]
