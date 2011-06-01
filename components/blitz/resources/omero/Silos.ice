/*
 *   $Id$
 *
 *   Copyright 2011 Glencoe Software, Inc. All rights reserved.
 *   Use is subject to license terms supplied in LICENSE.txt
 *
 */

#ifndef OMERO_SILO_ICE
#define OMERO_SILO_ICE

#include <omero/Collections.ice>
#include <omero/Repositories.ice>
#include <omero/ServerErrors.ice>
#include <omero/ServicesF.ice>

module omero {

    /*
     * Forward declaration
     */
    module api {
        interface ServiceFactory;
    };

    module grid {

        /**
         * Service responsible for securely storing structured data
         * based on third-party schemas previously unknown to the system.
         **/
        interface Silo extends Repository {

            /**
             *
             * throws ValidationError if the name already exists.
             **/
            long createSilo(string name)
                throws ServerError;

            void setSiloId(long id)
                throws ServerError;

            void setSilo(string name)
                throws ServerError;

            omero::api::StringSet listSilos()
                throws ServerError;

            void registerSchema(long originalFileID)
                throws ServerError;

            void addData(long originalFileID)
                throws ServerError;

        };

    //
    // Interfaces and types running the backend.
    // Used by OMERO.blitz to manage the public
    // omero.api types.
    // ========================================================================
    //

        // Possibly not needed in repository case.

        ["ami"] interface Silos {

            /**
             * Returns an uninitialized Silo service.
             */
            Silo*
                getSilo(omero::api::ServiceFactory* sf)
                throws omero::ServerError;


        };

    };

};

#endif
