from django.contrib import admin
from .models import (
    UserSubscription, 
    CreditTransaction, CreditBalance,
    ProcessedRevenueCatEvent,
    Transaction
)

# Register your models here.

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'product_id', 'credits_per_month', 'status', 'start_date', 'end_date', 'is_trial')
    search_fields = ('user__username', 'user__email', 'product_id', 'revenuecat_id')
    list_filter = ('status', 'is_trial')
    date_hierarchy = 'start_date'

@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'transaction_type', 'created_at')
    search_fields = ('user__username', 'user__email', 'reference_id')
    list_filter = ('transaction_type',)
    date_hierarchy = 'created_at'

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('from_user', 'to_user', 'amount', 'transaction_type', 'status', 'transaction_date')
    search_fields = ('from_user__username', 'from_user__email', 'to_user__username', 'to_user__email', 'stripe_payment_intent_id', 'stripe_transfer_id')
    list_filter = ('transaction_type', 'status')
    date_hierarchy = 'transaction_date'

@admin.register(CreditBalance)
class CreditBalanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'spectator_balance', 'creator_balance', 'last_updated')
    search_fields = ('user__username', 'user__email')

@admin.register(ProcessedRevenueCatEvent)
class ProcessedRevenueCatEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'user', 'product_id', 'processed_at')
    search_fields = ('event_id', 'user__username', 'user__email', 'product_id')
    list_filter = ('event_type',)
    date_hierarchy = 'processed_at'
    readonly_fields = ('event_id', 'event_type', 'user', 'product_id', 'processed_at')
