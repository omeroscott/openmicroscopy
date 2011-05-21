#!/usr/bin/env python
#
# OMERO Haven Interface
# Copyright 2011 Glencoe Software, Inc.  All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

import os
import Ice
import time
import numpy
import signal
import logging
import threading
import traceback
import subprocess
import exceptions
import portalocker # Third-party

from path import path


import omero # Do we need both??
import omero.clients
import omero.callbacks

# For ease of use
from omero.rtypes import *
from omero.util.decorators import remoted, locked, perf


class HavenI(omero.grid.Haven, omero.util.SimpleServant):
    """
    """

    def __init__(self, ctx, factory, uuid):
        self.uuid = uuid
        self.file_obj = file_obj
        self.factory = factory
        self.storage = storage
        self.can_write = factory.getAdminService().canUpdate(file_obj)
        omero.util.SimpleServant.__init__(self, ctx)

        self.stamp = time.time()
        self.storage.incr(self)

class HavensI(omero.grid.Haven, omero.util.Servant):
    """
    Implementation of the omero.grid.Haven API. Provides
    secure access to structured data from other schemas.

    Secure access entails primarily stringent auditing of
    all data input and output, down to the row or row/column
    level.
    """

    def __init__(self,\
        ctx,\
        haven_cast = omero.grid.HavenPrx.uncheckedCast,\
        internal_repo_cast = omero.grid.InternalRepositoryPrx.checkedCast):

        omero.util.Servant.__init__(self, ctx, needs_session = True)

        # Storing these methods, mainly to allow overriding via
        # test methods. Static methods are evil.
        self._table_cast = table_cast
        self._internal_repo_cast = internal_repo_cast

    @remoted
    @perf
    def getHaven(self, factory, current = None):
        """
        """
        id = Ice.Identity()
        id.name = Ice.generateUUID()
        haven = HavenI(self.ctx, factory, uuid = id.name)
        self.resources.add(haven)

        prx = current.adapter.add(haven, id)
        return self._haven_cast(prx)
