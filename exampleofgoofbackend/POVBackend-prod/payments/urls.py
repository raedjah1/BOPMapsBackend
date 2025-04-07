from django.urls import path
from .views import (
    add_payment_method, check_monetization_status, enable_monetization, 
    get_creator_balance, get_payment_methods, get_transactions, create_transaction, get_stripe_dashboard_url,
    send_tip, update_default_payment_method, delete_payment_method, update_revenuecat_uuid, withdraw_earnings,
    # Credit system views
    get_credit_balance, get_credit_transactions,
    get_user_subscription, webhook_revenuecat
)

urlpatterns = [
    path('transactions/', get_transactions, name='get_transactions'),
    path('create-transaction/', create_transaction, name='create_transaction'),
    path('send-tip/', send_tip, name='send_tip'),
    path('add_payment_method/', add_payment_method, name='add_payment_method'),
    path('get-payment-methods/', get_payment_methods, name='get_payment_methods'),
    path('update-default-payment-method/', update_default_payment_method, name='update_default_payment_method'),
    path('delete-payment-method/', delete_payment_method, name='delete_payment_method'),
    path('withdraw/', withdraw_earnings, name='withdraw_earnings'),
    path('enable-monetization/', enable_monetization, name='enable_monetization'),
    path('check-monetization-status/', check_monetization_status, name='check_monetization_status'),
    path('get-creator-balance/', get_creator_balance, name='get_creator_balance'),

    # Credit system endpoints
    path('credits/balance/', get_credit_balance, name='get_credit_balance'),
    path('credits/transactions/', get_credit_transactions, name='get_credit_transactions'),
    path('credits/subscription/', get_user_subscription, name='get_user_subscription'),
    
    # RevenueCat webhook
    path('webhooks/revenuecat/', webhook_revenuecat, name='webhook_revenuecat'),
    path('update-revenuecat-uuid/', update_revenuecat_uuid, name='update_revenuecat_uuid'),

    path('stripe-dashboard-url/', get_stripe_dashboard_url, name='get_stripe_dashboard_url'),
]