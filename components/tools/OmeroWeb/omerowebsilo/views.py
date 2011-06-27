from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template.loader import get_template
from django.template import Context
from django.views.decorators.csrf import csrf_exempt

import uuid
import sys
sys.path.append("/home/simon/apps/OMERO/OMERO.server/lib/python")
from omero.gateway import BlitzGateway
import omero
import omero.model
import omero.scripts as scripts
import omero.util.script_utils as scriptUtil
from omero.rtypes import *

@csrf_exempt
def import_datasets(request):

	newID =  uuid.uuid1()
	
	query = request.POST.get('id', '')
	if query:
		ID = query
		if ID:
			client = omero.client("127.0.0.1")
			session = client.createSession("root", "omero")
			updateService = session.getUpdateService()

			project = omero.model.ProjectI()
			project.name = rstring(str(ID))
			dataset = omero.model.DatasetI()
			dataset.name = rstring(str(ID))
			dataset.linkProject(project)

			ds = updateService.saveAndReturnObject(dataset)
	else:
		ID = ' '

	return render_to_response('import_datasets.html', {'datasetid' : newID})

def view_datasets(request):
	conn = BlitzGateway("root", "omero", host="localhost", port=4064)
	conn.connect()
	projectList = [project.getId() for project in conn.listProjects()]
	return render_to_response('view_datasets.html', {'projectlist' : projectList})
