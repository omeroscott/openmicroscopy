#!/usr/bin/env python
#
# OMERO Haven Runner
# Copyright 2011 Glencoe Software, Inc.  All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

if __name__ == "__main__":

    import sys
    import Ice
    import omero
    import omero.clients
    import omero.haven

    # Logging hack
    omero.haven.HavenI.__module__ = "omero.havens"
    omero.haven.HavensI.__module__ = "omero.havens"

    app = omero.util.Server(omero.haven.HavensI, "HavenAdapter", Ice.Identity("Haven", ""))
    sys.exit(app.main(sys.argv))
