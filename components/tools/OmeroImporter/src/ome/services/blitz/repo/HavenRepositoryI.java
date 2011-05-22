/*
 *   $Id$
 *
 *   Copyright 2011 Glencoe Software, Inc. All rights reserved.
 *   Use is subject to license terms supplied in LICENSE.txt
 */
package ome.services.blitz.repo;

import java.io.File;

import ome.services.blitz.fire.Registry;
import ome.services.util.Executor;
import ome.util.SqlAction;
import Ice.ObjectAdapter;

/**

 * @since Beta4.4
 */
public class HavenRepositoryI extends AbstractRepositoryI {

    public HavenRepositoryI(ObjectAdapter oa, Registry reg, Executor ex,
            SqlAction sql, String sessionUuid, String repoDir) {
        super(oa, reg, ex, sql, sessionUuid, repoDir);
    }

    @Override
    protected PublicRepositoryI createPublicRepository(
            ome.model.core.OriginalFile r) throws Exception {
        PublicHavenRepositoryI pr = new PublicHavenRepositoryI(new File(fileMaker
                .getDir()), r.getId(), ex, sql, p);
        return pr;
    }

}
