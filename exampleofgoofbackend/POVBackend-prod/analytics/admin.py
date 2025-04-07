from django.contrib import admin
from .models import SubscriptionSnapshot, ViewSnapshot, TipSnapshot, EngagementSnapshot, DemographicSnapshot, RevenueSnapshot

admin.site.register(SubscriptionSnapshot)
admin.site.register(ViewSnapshot)
admin.site.register(TipSnapshot)
admin.site.register(EngagementSnapshot)
admin.site.register(DemographicSnapshot)
admin.site.register(RevenueSnapshot)
