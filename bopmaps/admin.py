from django.contrib.admin import AdminSite
from django.shortcuts import redirect

class BopMapsAdminSite(AdminSite):
    site_header = 'BOPMaps Administration'
    site_title = 'BOPMaps Admin'
    index_title = 'BOPMaps Dashboard'
    
    def index(self, request, extra_context=None):
        # Redirect to the Users changelist as the default view
        return redirect('admin:users_user_changelist')

# Create an instance of the custom admin site
bopmaps_admin_site = BopMapsAdminSite(name='bopmaps_admin') 