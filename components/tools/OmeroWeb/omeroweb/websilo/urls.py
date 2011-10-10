from django.conf.urls.defaults import *
from django.views.static import serve

from omeroweb.websilo import views

urlpatterns = patterns('django.views.generic.simple',

    url( r'^statictest/(?P<path>.*)$', serve, {'document_root': 'media/websilo'}, name="statictest"),

    url( r'^$', views.index, name='websilo_index' ),
    url( r'^login/$', views.login, name='websilo_login' ),
    url( r'^logout/$', views.logout, name='websilo_logout' ),
    url(r'^view/$', views.view_datasets, name='websilo_view'),
    url(r'^view/(?P<datasetid>\d+)/$', views.view_dataset, name='websilo_view_dataset'),
	url(r'^view/(?P<datasetid>\d+)/(?P<tableid>\d+)/$', views.view_table, name='websilo_view_table'),
	url(r'^view/(?P<datasetid>\d+)/auditlog/$', views.view_auditlog, name='websilo_view_auditlog'),
	url(r'^view/alias/(?P<aliasid>\d+)/$', views.view_alias, name='websilo_view_alias'),
	url(r'^import/$', views.import_datasets, name='websilo_import'),
	url(r'^export/$', views.export_datasets, name='websilo_export'),
	url(r'^query/$', views.run_query, name='websilo_query'),
	url(r'^jobs/$', views.manage_jobs, name='websilo_jobs'),
	url(r'^audit/$', views.audit_silos, name='websilo_audit'),
	url(r'^admin/$', views.admin, name='websilo_admin'),
	url(r'^help/$', views.websilo_help, name='websilo_help'),
)
