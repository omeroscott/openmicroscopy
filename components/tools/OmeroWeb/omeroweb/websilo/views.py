from django.http import HttpResponseRedirect, HttpResponse
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response
from omeroweb.webgateway.views import getBlitzConnection, _session_logout
from omeroweb.webgateway import views as webgateway_views
from omeroweb.webclient.views import isUserConnected

from omero.plugins.silo import SiloApi
from omero.plugins.silo import SiloControl
from cStringIO import StringIO

import uuid

import settings
import logging
import traceback
import omero
import omero.columns
from omero.rtypes import rint, rstring
import omero.gateway
from omero.rtypes import *
logger = logging.getLogger('websilo')    

    
def login (request):
    """
    Attempts to get a connection to the server by calling L{omeroweb.webgateway.views.getBlitzConnection} with the 'request'
    object. If a connection is created, the user is directed to the 'websilo_index' page. 
    If a connection is not created, this method returns a login page.
    
    @param request:     The django http request
    @return:            The http response - websilo_index or login page
    """
    if request.method == 'POST' and request.REQUEST['server']:
        blitz = settings.SERVER_LIST.get(pk=request.REQUEST['server'])
        request.session['server'] = blitz.id
        request.session['host'] = blitz.host
        request.session['port'] = blitz.port
    
    conn = getBlitzConnection (request, useragent="OMERO.websilo")
    logger.debug(conn)
    if conn is not None:
        return HttpResponseRedirect(reverse('websilo_index'))
    return render_to_response('websilo/login.html', {'gw':settings.SERVER_LIST})


def logout (request):
    _session_logout(request, request.session['server'])
    try:
        del request.session['username']
    except KeyError:
        logger.error(traceback.format_exc())
    try:
        del request.session['password']
    except KeyError:
        logger.error(traceback.format_exc())
    
    #request.session.set_expiry(1)
    return HttpResponseRedirect(reverse('websilo_index'))


@isUserConnected    # wrapper handles login (or redirects to webclient login). Connection passed in **kwargs
def index(request, **kwargs):
    conn = kwargs['conn']
    return render_to_response('websilo/index.html', {'client': conn})

@isUserConnected
def view_datasets(request, **kwargs):
	#conn = kwargs['conn']
	
	#projectList = [project.getId() for project in conn.listProjects()]
	#return render_to_response('websilo/view_silos.html', {'projectlist' : projectList})

	# SiloApi doesn't seem to work with blitz connection so creating a regular omero.client connection for now
	conn = omero.client("127.0.0.1")
	session = conn.createSession("root", "omero")
	tmpsilo = SiloApi(conn, None)

	silolist = tmpsilo.list(0,100)	
	return render_to_response('websilo/view_silos.html', {'silolist' : silolist})

@isUserConnected    
def import_datasets(request, **kwargs):
	from omero.grid import StringColumn, LongColumn

	UUID =  uuid.uuid1()
	siloname = "silo_" + str(UUID)
	query = request.POST.get('id', '')
	if query:
		name = query
		if name:
			#conn = kwargs['conn']
			#updateService = conn.getUpdateService()

			#project = omero.model.ProjectI()
			#project.name = rstring(str(ID))
			#dataset = omero.model.DatasetI()
			#dataset.name = rstring(str(ID))
			#dataset.linkProject(project)

			#ds = updateService.saveAndReturnObject(dataset)

			conn = omero.client("127.0.0.1")
			session = conn.createSession("root", "omero")
			newsilo = SiloApi(conn, conn.sf.getAdminService().getEventContext())
			siloid = newsilo.create(str(name))

			# Create AuditLog

			cols = []
			cols.append( omero.columns.LongColumnI("user_id", "", None) )
			cols.append( omero.columns.LongColumnI("timestamp", "", None) )
			cols.append( omero.columns.StringColumnI("resource", "", 100, None) )
			cols.append( omero.columns.StringColumnI("action", "", 100, None) )
			cols.append( omero.columns.StringColumnI("message", "", 100, None) )
			logging.info(cols)
			newsilo.define(siloid, "AuditLog", cols, skip_audit = True)
			
			# Create demo table
			tableCols = []
			tableCols.append( omero.columns.StringColumnI("personal_id", "", 12, None) )
			tableCols.append( omero.columns.LongColumnI("measurement_1", "", None) )
			tableCols.append( omero.columns.LongColumnI("measurement_2", "", None) )
			logging.info(tableCols)
			of =  newsilo.define(siloid, "TypeA", tableCols, skip_audit = False)
			tableid = of.id.val
			
			cs = newsilo.headers(tableid)
			for c in cs:
				c.values = []
			for x in range(50):
				cs[0].values.append(("%s" % x) * 12)
				cs[1].values.append(x)
				cs[2].values.append(-x)
			newsilo.write(tableid, cs)
			
			#logging.info("websilo :: "+str(tableid))
			#tables = newsilo.tables(198,0,100)
			#logging.info(tables)
			
			
			
			
			return render_to_response('websilo/import_datasets.html', {'siloname' : siloname})
	else:
		name = ' '

	return render_to_response('websilo/import_datasets.html', {'siloname' : siloname})

@isUserConnected
def export_datasets(request, **kwargs):
	conn = kwargs['conn']
	return render_to_response('websilo/export_datasets.html', {'client': conn})

@isUserConnected
def run_query(request, **kwargs):
	conn = kwargs['conn']
	return render_to_response('websilo/run_query.html', {'client': conn})

@isUserConnected
def manage_jobs(request, **kwargs):
	conn = kwargs['conn']
	return render_to_response('websilo/manage_jobs.html', {'client': conn})

@isUserConnected
def audit_silos(request, **kwargs):
	conn = kwargs['conn']
	return render_to_response('websilo/audit_silos.html', {'client': conn})

@isUserConnected
def admin(request, **kwargs):
	conn = kwargs['conn']
	return render_to_response('websilo/admin.html', {'client': conn})

@isUserConnected
def websilo_help(request, **kwargs):
	conn = kwargs['conn']
	return render_to_response('websilo/help.html', {'client': conn})