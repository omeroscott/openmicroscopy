/*
 * ome.services.blitz.repo.PublicRepositoryI
 *
 *------------------------------------------------------------------------------
 *  Copyright (C) 2006-2010 University of Dundee. All rights reserved.
 *
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 *------------------------------------------------------------------------------
 *
 *
 */
package ome.services.blitz.repo;

import java.io.File;
import java.util.List;

import ome.services.util.Executor;
import ome.system.Principal;
import ome.util.SqlAction;
import omero.ServerError;
import omero.api.ServiceFactoryPrx;
import omero.grid.SiloPrx;
import omero.grid._SiloOperations;
import Ice.Current;

/**
 * An extension of {@link PublicRepositoryI} for managing a silo storage
 * facility.
 *
 * @author Josh Moore, josh at glencoesoftware.com
 */
public class PublicSiloI extends PublicRepositoryI implements _SiloOperations {

    /**
     *
     */
    private static final long serialVersionUID = 1L;

    public PublicSiloI(File root, long repoObjectId,
            Executor executor, SqlAction sql, Principal principal)
            throws Exception {
        super(root, repoObjectId, executor, sql, principal);
    }

    public SiloPrx getSilo(ServiceFactoryPrx sf, Current __current)
            throws ServerError {
        return null;
    }

    //
    // Silo methods
    //

    public long createSilo(String name, Current __current) throws ServerError {
        // TODO Auto-generated method stub
        return 0;
    }

    public void setSiloId(long id, Current __current) throws ServerError {
        // TODO Auto-generated method stub

    }

    public void setSilo(String name, Current __current) throws ServerError {
        // TODO Auto-generated method stub

    }

    public List<String> listSilos(Current __current) throws ServerError {
        // TODO Auto-generated method stub
        return null;
    }

    public void registerSchema(long originalFileID, Current __current)
            throws ServerError {
        // TODO Auto-generated method stub

    }

    public void addData(long originalFileID, Current __current)
            throws ServerError {
        // TODO Auto-generated method stub

    }

}
