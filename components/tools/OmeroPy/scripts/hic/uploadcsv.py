import omero
import omero.model
import omero.scripts as scripts
import omero.util.script_utils as scriptUtil
from omero.rtypes import *

import datetime
import uuid
import os


def cleanString(input):
    """
    Replaces spaces and colons in the input string with underscores or dashes.
    This is useful when generating filenames because sane filenames don't contain
    certain characters, such as spaces, and some characters are treated differently
    by different filesystems, for example colons don't play nicely on OS X and have to be escaped.

    Returns:    A string
    """
    input = input.replace(' ', '_')
    input = input.replace(':', '-')
    return input


def createDataset(parent=None, name=None, date=False):
    """
    Create a new dataset object from various passed in parameters

    Arguments:
        name
            A string that is used to name the new project.
        parent
            The omero.model.ProjectI object to link this dataset to.
            If parent is none then an orphan dataset is created.
        date
            If a name is not supplied and date=False then a uuid is
            generated and used as the name. If a name is not supplied
            and date=True then the current date and time are used to
            generate a name.

    Returns:    omero.model.DataSetI
    """
    if name is None:
        if date is True:
            name = generateDateBasedFileName()
        else:
            name = uuid.uuid1()

    dataset = omero.model.DatasetI()
    dataset.name = rstring(str(name))
    if parent is not None:
        dataset.linkProject(parent)
    return dataset


def createProject(name=None, date=False):
    """
    Create a new project object.

    Arguments:
        name
            A string that is used to name the new project.
        date
            If a name is not supplied and date=False then a uuid
            is generated and used as the name. If a name is not
            supplied and date=True then the current date and time
            are used to generate a name.

    Returns:    An omero.model.ProjectI
    """
    if name is None:
        if date is True:
            name = generateDateBasedFileName()
        else:
            name = uuid.uuid1()

    project = omero.model.ProjectI()
    project.name = rstring(str(name))
    return project


def generateDateBasedFileName():
    """
    Used to automatically generate a filename using the current date and time.

    Returns:    a string containing the newly generated filename
    """
    today = datetime.datetime.today()
    name = str(today)
    name = cleanString(name)
    return name


def runAsScript():
    # NB. Assumes *nix for now TODO: Make platform agnostic
    rawfilelist = os.listdir("/home/omero/scripts/omero-hic/")
    files = [rstring(file) for file in rawfilelist]

    client = scripts.client('uploadcsv.py', """ """)
    try:
        session = client.getSession()
        gateway = session.createGateway()
        projects = gateway.getProjects(None, False)
    finally:
        client.closeSession()

    if len(projects) > 0:
        for project in projects:
            print project.getName()
    else:
        print "no projects found!"

    client = scripts.client('uploadcsv.py', """uploadcsv.py

    An OMERO.script to import CSV formatted medical informatics datasets into OMERO.

    1. Create a new Project & Dataset for this user on the OMERO.server.
    2. Upload a CSV file and attach it to the newly created dataset for subsequent use.""",
            scripts.String("Input Data", description="Data to import into OMERO", grouping="1", values=files),
            scripts.String("Project Name", description="Project to add this data to", grouping="2"),
            scripts.String("Dataset Name", description="Dataset to hold input data", grouping="3"),
            version = "4.2.0",
            authors = ["Simon Wells", "OME/HIC"],
            institutions = ["University of Dundee"],
            contact = "ome-users@lists.openmicroscopy.org.uk",
        )

    try:
        session = client.getSession()
        updateService = session.getUpdateService()
        #gateway = session.createGateway()

        project = createProject(None, True)

#TODO: Move to unit testing
#        for num in xrange(1,6):
#            dsname = "dataset"+str(num)
#            ds = createDataset(project,dsname)

        ds = createDataset(project, None, True)

#        updateService.saveObject(project)
#        project = updateService.saveAndReturnObject(project)
        dataset = updateService.saveAndReturnObject(ds)
#        print project.getId().getValue()

        queryService = session.getQueryService()
        rawFileStore = session.createRawFileStore()
#        print dataset.getId().getValue()

        filepath = "/home/omero/scripts/omero-hic/test.csv"
        mimetype = "text/csv"

        fileAnnotation = scriptUtil.uploadAndAttachFile(\
            queryService, updateService, rawFileStore, dataset, filepath, mimetype)

        client.setOutput("Message", rstring("DONE!"))
    finally:
        client.closeSession()

if __name__ == '__main__':
    runAsScript()
