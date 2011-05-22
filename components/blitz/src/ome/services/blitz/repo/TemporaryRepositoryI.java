/*
 *   $Id$
 *
 *   Copyright 2009 Glencoe Software, Inc. All rights reserved.
 *   Use is subject to license terms supplied in LICENSE.txt
 */
package ome.services.blitz.repo;

import ome.services.blitz.fire.Registry;
import ome.services.util.Executor;
import ome.util.SqlAction;

/**
 * Simple repository service to make the ${java.io.tmpdir} available at runtime.
 * This is primarily for testing (see blitz-config.xml to disable) of the
 * repository infrastructure, and will lead to a number of repository objects
 * being created in the database.
 *
 * @since Beta4.1
 */
public class TemporaryRepositoryI extends AbstractRepositoryI {

    public TemporaryRepositoryI(Ice.ObjectAdapter oa, Registry reg,
            Executor ex, SqlAction sql, String sessionUuid) {
        super(oa, reg, ex, sql, sessionUuid, System.getProperty("java.io.tmpdir"));
    }

}
