# payments/serializers.py
from rest_framework import serializers
from .models import (
    Transaction, Tip, CreditTransaction, 
    CreditBalance, UserSubscription
)
from users.serializers import UserSerializer

class TransactionSerializer(serializers.ModelSerializer):
    from_user = UserSerializer(read_only=True)
    to_user = UserSerializer(read_only=True)
    
    class Meta:
        model = Transaction
        fields = '__all__'
        read_only_fields = ['pk', 'transaction_date']

class TipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tip
        fields = '__all__'

class CreditTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditTransaction
        fields = ['id', 'amount', 'transaction_type', 'created_at', 'metadata']

class CreditBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditBalance
        fields = ['balance', 'last_updated']

class UserSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSubscription
        fields = [
            'id', 'product_id', 'credits_per_month', 'status', 'start_date', 
            'end_date', 'last_renewal_date', 'next_renewal_date'
        ]
