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
import Ice.ObjectAdapter;

/**
 * Standalone repository service.
 *
 * @DEV.TODO Better named "StandaloneRepositoryI"
 * @since Beta4.1
 */
public class InternalRepositoryI extends AbstractRepositoryI {

    public InternalRepositoryI(ObjectAdapter oa, Registry reg, Executor ex,
            SqlAction sql, String sessionUuid, String repoDir) {
        super(oa, reg, ex, sql, sessionUuid, repoDir);
    }

}
