from django.conf.urls.defaults import *
from django.views.static import serve

from omeroweb.websilo import views

urlpatterns = patterns('django.views.generic.simple',

    url( r'^statictest/(?P<path>.*)$', serve, {'document_root': 'media/websilo'}, name="statictest"),

    url( r'^$', views.index, name='websilo_index' ),
    url( r'^login/$', views.login, name='websilo_login' ),
    url( r'^logout/$', views.logout, name='websilo_logout' ),
    url(r'^datasets/$', views.view_datasets, name='websilo_datasets'),
	url(r'^import/$', views.import_datasets, name='websilo_import'),
)
