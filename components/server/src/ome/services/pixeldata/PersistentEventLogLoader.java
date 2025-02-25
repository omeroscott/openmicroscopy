/*
 *   $Id$
 *
 *   Copyright 2011 Glencoe Software, Inc. All rights reserved.
 *   Use is subject to license terms supplied in LICENSE.txt
 */

package ome.services.pixeldata;

import java.util.Arrays;
import java.util.List;

import ome.model.meta.EventLog;
import ome.services.eventlogs.EventLogLoader;

/**
 * {@link EventLogLoader} implementation which keeps tracks of the last
 * {@link EventLog} instance, and always provides the next unindexed instance.
 * Reseting that saved value would restart indexing.
 *
 * @author Josh Moore, josh at glencoesoftware.com
 * @since Beta4.3
 */
public class PersistentEventLogLoader extends ome.services.eventlogs.PersistentEventLogLoader {

    protected final String repo;

    /**
     * The lowest entity id from a single dataPerUser set.
     */
    protected long lowestEntityId = -1;

    protected List<long[]> dataPerUser = null;
    
    public PersistentEventLogLoader(String repo) {
        this.repo = repo;
    }
    
    @Override
    public void initialize() {
        // no-op
    }
    
    /**
     * Uses data from the {@link #dataPerUser} "queue" to allow new requests to
     * be processed even if one user adds a large number of PIXELDATA events.
     * Only the lowest event log id will be saved as the {@link #getCurrentId()}
     * meaning that some event logs will be processed multiple times. The call
     * to create the pyramid must properly ignore existing pyramids.
     */
    @Override
    protected EventLog query() {

        if (available()) {
            return pop();
        } else {
            final long current_id = getCurrentId();
            if (log.isDebugEnabled()) {
                log.debug(String.format(
                        "Locating next PIXELSDATA EventLog repo:%s > id:%d",
                        repo, current_id));
            }
            dataPerUser = sql.nextPixelsDataLogForRepo(repo, current_id);
            if (log.isDebugEnabled()) {
                for (long[] data : dataPerUser) {
                    log.debug("Data: " + Arrays.toString(data));
                }
            }
            if (available()) {
                return pop();
            }
        }

        return null;
    }

    protected boolean available() {
        return dataPerUser != null && dataPerUser.size() > 0;
    }

    protected EventLog pop() {

        if (!available()) {
            throw new IllegalStateException();
        }

        long[] data = dataPerUser.remove(0);
        final long experimenter = data[0];
        final long eventLog = data[1];
        final long pixels = data[2];

        if (log.isDebugEnabled()) {
            log.debug(String.format("Handling pixels id:%d for user id:%d",
                    pixels, experimenter));
        }

        // Store the lowest of the entity ids.
        if (lowestEntityId < 0) {
            lowestEntityId = eventLog;
        } else {
            if (lowestEntityId > eventLog) {
                lowestEntityId = eventLog;
            }
        }

        // If we are finished, then save this as current id
        if (!available()) {
            dataPerUser = null;
            try {
                setCurrentId(lowestEntityId);
            } finally {
                lowestEntityId = -1;
            }
        }

        return queryService.get(EventLog.class, eventLog);

    }

}
