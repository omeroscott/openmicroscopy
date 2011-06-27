from django.conf.urls.defaults import *
from omerowebsilo import settings
from omerowebsilo.views import *

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    # Example:
    # (r'^omerowebsilo/', include('omerowebsilo.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # (r'^admin/', include(admin.site.urls)),
	(r'^datasets/$', view_datasets),
	(r'^import/$', import_datasets),
)
if settings.DEBUG:
	urlpatterns += patterns('',
    (r'^media/(?P<path>.*)$', 'django.views.static.serve',  
     {'document_root':     settings.MEDIA_ROOT}),
)
