from django.http import HttpResponseRedirect, HttpResponse
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response
from omeroweb.webgateway.views import getBlitzConnection, _session_logout
from omeroweb.webgateway import views as webgateway_views
from omeroweb.webclient.views import isUserConnected

from cStringIO import StringIO

import uuid

import settings
import logging
import traceback
import omero
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
def import_datasets(request, **kwargs):

	newID =  uuid.uuid1()
	
	query = request.POST.get('id', '')
	if query:
		ID = query
		if ID:
			#client = omero.client("127.0.0.1")
			#session = client.createSession("root", "omero")
			conn = kwargs['conn']
			updateService = conn.getUpdateService()

			project = omero.model.ProjectI()
			project.name = rstring(str(ID))
			dataset = omero.model.DatasetI()
			dataset.name = rstring(str(ID))
			dataset.linkProject(project)

			ds = updateService.saveAndReturnObject(dataset)
	else:
		ID = ' '

	return render_to_response('websilo/import_datasets.html', {'datasetid' : newID})

@isUserConnected
def view_datasets(request, **kwargs):
	conn = kwargs['conn']
	#conn = BlitzGateway("root", "omero", host="localhost", port=4064)
	#conn.connect()
	projectList = [project.getId() for project in conn.listProjects()]
	return render_to_response('websilo/view_datasets.html', {'projectlist' : projectList})
