#!/usr/bin/env python

"""
   Test of the Silos service

   Copyright 2011 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import path
import unittest, os

#import omero, omero.silos
#from omero.rtypes import *
#from integration import library as lib
class lib(object):
    ITest = unittest.TestCase

class EventLog(object):
    def __init__(self, action, entityType, entityId):
        self.action = action
        self.entityType = entityType
        self.entityId = entityId

class Column(object):
    def __init__(self, name, description, originalName, originalPosition):
        self.name = name
        self.description = description
        self.originalName = originalName
        self.originalPosition = originalPosition
class Silo(object):
    def __init__(self):
        self.name = "test"
        self.types = ["patient", "prescription"]
        self.columns = {"patient":[Column("prochi","","prochi",1)], "prescription":[Column("pres","","pres",1)]}
        self.data = {}
        self.row_access = False
        self.logs = []
    def setRecordRowAccess(self, v):
        self.row_access = v
        self.logs.append(EventLog("%s"%v, "Settings:RecordRowAccess", -1))
    def getEventLogs(self):
        return list(self.logs)
    def getTypes(self):
        return list(self.types)
    def getColumns(self, name):
        return self.columns[name]
    def addType(self, name, originalFile):
        self.types.append(name)
        self.columns[name] = [Column("unknown","","unknown",0)]
    def addData(self, name, originalfile):
        try:
            self.data[name].append(originalfile)
        except KeyError:
            self.data[name] = [originalfile]

class client(object):
    @staticmethod
    def upload(*args):
        return object()

silo_prx = Silo()

class TestSilos(lib.ITest):

    def testSimple(self):

        if False: ##### Possible service styles ####

            grid = self.client.sf.sharedResources()

            # Pure repo solution. Need to under
            repoMap = grid.repositories() # Returns "Repository" mimetype
            repoMap = grid.repositoriesOfType("Silo") # Mimetype
            hic = "..." # Get the appropriate on somehow
            hic.list("/")
            hic.mkdir("/Patients")
            hic.attachAgent("/Patients", "SiloType", {"schema":original_file_id})
            client.upload("/Patients", "test.csv")

            # Shared resource solution
            grid.deleteSilo("test")
            grid.createSilo("test")
            grid.findSilo("test")
            silo_prx = grid.getRepositoryForSilo(silo_obj)

            # Share solution
            silo_obj = iSharePrx.creatShare("...", silo = True)

            # Object solution
            silo_prx = grid.findSilo("test")
            silo_prx = grid.openSilo(SiloI(1, False))

            # Or is the repo a group, i.e. a shared pot?!?!?!

            # Negative tests
            assertRaises(createSilo, "no.periods")
            assertRaises(createSilo, "no spaces")
            assertRaises(createSilo, "no_punctunation")
            assertRaises(createSilo, "no-punctunation")

        # Result of the above should be a single silo prx
        silo_prx = Silo()

        # Admin
        original_file = client.upload("test.xml")
        silo_prx.addType("test", original_file)

        original_file = client.upload("test.csv")
        silo_prx.addData("test", original_file)

        # Audit settings
        silo_prx.setRecordRowAccess(True)


        # Audit information
        logs = silo_prx.getEventLogs() # Return own ITime
        for log in logs:
            print log.action,
            print log.entityType, # "<TYPE>.<columnname>
            print log.entityId,   # row, -1 for no record row access

        # User
        names = silo_prx.getTypes()
        for name in names:
            print name

            cols = silo_prx.getColumns(name)
            for col in cols:
                print col.name,
                print col.description,
                print col.originalName,
                print col.originalPosition




def test_suite():
    return 1

if __name__ == '__main__':
    unittest.main()
