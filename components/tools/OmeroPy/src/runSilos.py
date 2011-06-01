#!/usr/bin/env python
#
# OMERO Silo Runner
# Copyright 2011 Glencoe Software, Inc.  All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

if __name__ == "__main__":

    import sys
    import Ice
    import omero
    import omero.clients
    import omero.silos

    # Logging hack
    omero.silos.SiloI.__module__ = "omero.silos"
    omero.silos.SilosI.__module__ = "omero.silos"

    app = omero.util.Server(omero.silos.SilosI, "SiloAdapter", Ice.Identity("Silo", ""))
    sys.exit(app.main(sys.argv))
