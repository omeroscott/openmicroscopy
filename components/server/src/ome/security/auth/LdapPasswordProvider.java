/*
 *   $Id$
 *
 *   Copyright 2009 Glencoe Software, Inc. All rights reserved.
 *   Use is subject to license terms supplied in LICENSE.txt
 */

package ome.security.auth;

import java.security.Permissions;

import ome.conditions.ApiUsageException;
import ome.logic.LdapImpl;
import ome.security.SecuritySystem;

import org.springframework.util.Assert;

/**
 * LDAP {@link PasswordProvider} which can create users on
 * {@link #checkPassword(String, String) request} to synchronize with an LDAP
 * directory. Assuming that a user exists in the configured LDAP store but not
 * in the database, then a new user will be created. Authentication, however,
 * always takes place against LDAP, and changing passwords is not allowed.
 * 
 * Note: deleted LDAP users will not be removed from OMERO, but will not be able
 * to login.
 * 
 * @author Josh Moore, josh at glencoesoftware.com
 * @see SecuritySystem
 * @see Permissions
 * @since 4.0
 */

public class LdapPasswordProvider extends ConfigurablePasswordProvider {

    final protected LdapImpl ldapUtil;

    public LdapPasswordProvider(PasswordUtil util, LdapImpl ldap) {
        super(util);
        Assert.notNull(ldap);
        this.ldapUtil = ldap;
    }

    public LdapPasswordProvider(PasswordUtil util,
            LdapImpl ldap,
            boolean ignoreUnknown) {
        super(util, ignoreUnknown);
        Assert.notNull(ldap);
        this.ldapUtil = ldap;
    }

    /**
     * Only returns if the user is already in the database and has a DN value in
     * the password table. Note: after a call to
     * {@link #checkPassword(String, String)} with this same user value, this
     * method might begin to return true due to a call to
     * {@link LocalLdap#createUserFromLdap(String, String)}.
     */
    @Override
    public boolean hasPassword(String user) {
        if (ldapUtil.getSetting()) {
            Long id = util.userId(user);
            if (id != null) {
                String dn = ldapUtil.lookupLdapAuthExperimenter(id);
                if (dn != null) {
                    return true;
                }
            }
        }
        return false;
    }

    @Override
    public Boolean checkPassword(String user, String password, boolean readOnly) {

        if (!ldapUtil.getSetting()) {
            return null; // EARLY EXIT!
        }

        Long id = util.userId(user);

        // Unknown user. First try to create.
        if (null == id) {
            try {
                if (readOnly == true) {
                    throw new IllegalStateException("Cannot create user!");
                }
                boolean login = ldapUtil.createUserFromLdap(user, password);
                // Use default logic if the user creation did not exist,
                // because there may be another non-database login mechanism
                // which should also be given a chance.
                if (login) {
                    loginAttempt(user, true);
                    return true;
                }
            } catch (ApiUsageException e) {
                log.info(String.format(
                        "Default choice on create user: %s (%s)", user, e));
            }
        }

        // Known user
        else {
            try {
                String dn = ldapUtil.lookupLdapAuthExperimenter(id);
                if (dn != null) {
                    return loginAttempt(user,
                            ldapUtil.validatePassword(dn, password));
                }
            } catch (ApiUsageException e) {
                log.warn("Default choice on check ldap password: " + user, e);
            }
        }

        // If anything goes wrong, use the default (configurable) logic.
        return super.checkPassword(user, password, readOnly);
    }

}
