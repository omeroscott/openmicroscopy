/*
 *   $Id$
 *
 *   Copyright 2009 Glencoe Software, Inc. All rights reserved.
 *   Use is subject to license terms supplied in LICENSE.txt
 */
package ome.services.blitz.repo;

import ome.services.blitz.fire.Registry;
import ome.services.scripts.ScriptRepoHelper;
import ome.services.util.Executor;
import ome.util.SqlAction;
import omero.ServerError;
import omero.model.OriginalFile;
import Ice.Current;
import Ice.ObjectAdapter;

/**
 * Repository which makes the included script files available to users.
 *
 * @since Beta4.2
 */
public class ScriptRepositoryI extends AbstractRepositoryI {

    private final ScriptRepoHelper helper;

    public ScriptRepositoryI(ObjectAdapter oa, Registry reg, Executor ex, SqlAction sql,
            String sessionUuid, ScriptRepoHelper helper) {
        super(oa, reg, ex, sql, sessionUuid, helper.getScriptDir());
        this.helper = helper;
    }

    @Override
    public String generateRepoUuid() {
        return this.helper.getUuid();
    }

    /**
     */
    public String getFilePath(final OriginalFile file, Current __current)
            throws ServerError {

        String repo = getFileRepo(file);
        String uuid = getRepoUuid();

        if (repo == null || !repo.equals(uuid)) {
            throw new omero.ValidationException(null, null,repo
                    + " does not belong to this repository: " + uuid);
        }

        return file.getPath() == null ? null : file.getPath().getValue();

    }

}
