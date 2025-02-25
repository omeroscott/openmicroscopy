# -*- coding: utf-8 -*-
#
# blitz_gateway - python bindings and wrappers to access an OMERO blitz server
# 
# Copyright (c) 2007, 2010 Glencoe Software, Inc. All rights reserved.
# 
# This software is distributed under the terms described by the LICENCE file
# you can find at the root of the distribution bundle, which states you are
# free to use it only for non commercial purposes.
# If the file is missing please request a copy by contacting
# jason@glencoesoftware.com.

# Set up the python include paths
import os,sys
THISPATH = os.path.dirname(os.path.abspath(__file__))

import shutil
import tempfile
from types import IntType, LongType, UnicodeType, ListType, TupleType, StringType, StringTypes
from datetime import datetime
from cStringIO import StringIO
import ConfigParser

import omero
import omero.clients
from omero.util.decorators import timeit, TimeIt
import Ice
import Glacier2

import traceback
import time
import array

import logging
logger = logging.getLogger('blitz_gateway')

try:
    import Image, ImageDraw, ImageFont
except: #pragma: nocover
    try:
        from PIL import Image, ImageDraw, ImageFont
    except:
        logger.error('No PIL installed, line plots and split channel will fail!')
from cStringIO import StringIO
from math import sqrt

import omero_Constants_ice  
import omero_ROMIO_ice
from omero.rtypes import rstring, rint, rlong, rbool, rtime, rlist, rdouble

def omero_type(val):
    """
    Converts rtypes from static factory methods:
      - StringType to rstring
      - UnicodeType to rstring
      - IntType to rint
      - LongType to rlong
    elswere return the argument itself

    @param val: value 
    @rtype:     omero.rtype
    @return:    matched RType or value
    """
    
    if isinstance(val, StringType):
        return rstring(val)
    elif isinstance(val, UnicodeType):
        return rstring(val.encode('utf-8'))
    elif isinstance(val, IntType):
        return rint(val)
    elif isinstance(val, LongType):
        return rlong(val)
    else:
        return val

def fileread (fin, fsize, bufsize):
    """
    Reads everything from fin, in chunks of bufsize.

    
    @type fin: file
    @param fin: filelike readable object
    @type fsize: int
    @param fsize: total number of bytes to read
    @type bufsize: int
    @param fsize: size of each chunk of data read from fin
    @rtype: string
    @return: string buffer holding the contents read from the file
    """
    # Read it all in one go
    p = 0
    rv = ''
    while p < fsize:
        s = min(bufsize, fsize-p)
        rv += fin.read(p,s)
        p += s
    fin.close()
    return rv
    

def fileread_gen (fin, fsize, bufsize):
    """
    Generator helper function that yields chunks of the file of size fsize. 

    @type fin: file
    @param fin: filelike readable object
    @type fsize: int
    @param fsize: total number of bytes to read
    @type bufsize: int
    @param fsize: size of each chunk of data read from fin that gets yielded
    @rtype: generator
    @return: generator of string buffers of size up to bufsize read from fin
    """
    p = 0
    while p < fsize:
        s = min(bufsize, fsize-p)
        yield fin.read(p,s)
        p += s
    fin.close()

class BlitzObjectWrapper (object):
    """
    Object wrapper class which provides various methods for hierarchy traversing, 
    saving, handling permissions etc. 
    This is the 'abstract' super class which is subclassed by 
    E.g. _ProjectWrapper, _DatasetWrapper etc. 
    All ojbects have a reference to the L{BlitzGateway} connection, and therefore all services are
    available for handling calls on the object wrapper. E.g listChildren() uses queryservice etc.
    """
    
    OMERO_CLASS = None              # E.g. 'Project', 'Dataset', 'Experimenter' etc. 
    LINK_CLASS = None
    CHILD_WRAPPER_CLASS = None
    PARENT_WRAPPER_CLASS = None
    
    def __init__ (self, conn=None, obj=None, cache=None, **kwargs):
        """
        Initialises the wrapper object, setting the various class variables etc
        
        @param conn:    The L{omero.gateway.BlitzGateway} connection.
        @type conn:     L{omero.gateway.BlitzGateway}
        @param obj:     The object to wrap. E.g. omero.model.Image
        @type obj:      omero.model object
        @param cache:   Cache which is passed to new child wrappers
        """
        self.__bstrap__()
        self._obj = obj
        self._cache = cache
        if self._cache is None:
            self._cache = {}
        self._conn = conn
        self._creationDate = None
        if conn is None:
            return
        if hasattr(obj, 'id') and obj.id is not None:
            self._oid = obj.id.val
            if not self._obj.loaded:
                self._obj = self._conn.getQueryService().get(self._obj.__class__.__name__, self._oid)
        self.__prepare__ (**kwargs)

    def __eq__ (self, a):
        """
        Returns true if the object is of the same type and has same id and name
        
        @param a:   The object to compare to this one
        @return:    True if objects are same - see above
        @rtype:     Boolean
        """
        return type(a) == type(self) and self._obj.id == a._obj.id and self.getName() == a.getName()

    def __bstrap__ (self):
        """ Initialisation method which is implemented by subclasses to set their class variables etc. """
        pass

    def __prepare__ (self, **kwargs):
        """ Initialisation method which is implemented by subclasses to handle various init tasks """
        pass

    def __repr__ (self):
        """
        Returns a String representation of the Object, including ID if set. 
        
        @return:    String E.g. '<DatasetWrapper id=123>'
        @rtype:     String
        """
        if hasattr(self, '_oid'):
            return '<%s id=%s>' % (self.__class__.__name__, str(self._oid))
        return super(BlitzObjectWrapper, self).__repr__()
        
    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("Project")
        """
        return "select obj from %s obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent" % self.OMERO_CLASS

    def _getChildWrapper (self):
        """
        Returns the wrapper class of children of this object. 
        Checks that this is one of the Wrapper objects in the L{omero.gateway} module
        Raises NotImplementedError if this is not true or class is not defined (None)
        This is used internally by the L{listChildren} and L{countChildren} methods. 
        
        @return:    The child wrapper class. E.g. omero.gateway.DatasetWrapper.__class__
        @rtype:     class
        """
        if self.CHILD_WRAPPER_CLASS is None:
            raise NotImplementedError('%s has no child wrapper defined' % self.__class__)
        if type(self.CHILD_WRAPPER_CLASS) is type(''):
            # resolve class
            if hasattr(omero.gateway, self.CHILD_WRAPPER_CLASS):
                self.__class__.CHILD_WRAPPER_CLASS = self.CHILD_WRAPPER_CLASS = getattr(omero.gateway, self.CHILD_WRAPPER_CLASS)
            else: #pragma: no cover
                raise NotImplementedError
        return self.CHILD_WRAPPER_CLASS

    def _getParentWrapper (self):
        """
        Returns the wrapper class of the parent of this object. 
        This is used internally by the L{listParents} method.
        
        @return:    The parent wrapper class. E.g. omero.gateway.DatasetWrapper.__class__
        @rtype:     class
        """
        if self.PARENT_WRAPPER_CLASS is None:
            raise NotImplementedError
        if type(self.PARENT_WRAPPER_CLASS) is type(''):
            # resolve class
            g = globals()
            if not g.has_key(self.PARENT_WRAPPER_CLASS): #pragma: no cover
                raise NotImplementedError
            self.__class__.PARENT_WRAPPER_CLASS = self.PARENT_WRAPPER_CLASS = g[self.PARENT_WRAPPER_CLASS]
        return self.PARENT_WRAPPER_CLASS

    def __loadedHotSwap__ (self):
        """
        Loads the object that is wrapped by this class. This includes linked objects. 
        This method can be overwritten by subclasses that want to specify how/which linked objects 
        are loaded. 
        """
        self._obj = self._conn.getContainerService().loadContainerHierarchy(self.OMERO_CLASS, (self._oid,), None)[0]

    def _moveLink (self, newParent):
        """ 
        Moves this object from a parent container (first one if there are more than one) to a new parent.
        TODO: might be more useful if it didn't assume only 1 parent - option allowed you to specify the oldParent.
        
        @param newParent:   The new parent Object Wrapper. 
        @return:            True if moved from parent to parent. 
                            False if no parent exists or newParent has mismatching type
        @rtype:             Boolean
        """
        p = self.getParent()
        # p._obj.__class__ == p._obj.__class__ ImageWrapper(omero.model.DatasetI())
        if p.OMERO_CLASS == newParent.OMERO_CLASS:
            link = self._conn.getQueryService().findAllByQuery("select l from %s as l where l.parent.id=%i and l.child.id=%i" % (p.LINK_CLASS, p.id, self.id), None)
            if len(link):
                link[0].parent = newParent._obj
                self._conn.getUpdateService().saveObject(link[0])
                return True
            logger.debug("## query didn't return objects: 'select l from %s as l where l.parent.id=%i and l.child.id=%i'" % (p.LINK_CLASS, p.id, self.id))
        else:
            logger.debug("## %s != %s ('%s' - '%s')" % (type(p), type(newParent), str(p), str(newParent)))
        return False

    def findChildByName (self, name, description=None):
        """
        Find the first child object with a matching name, and description if specified.
        
        @param name:    The name which must match the child name
        @param description: If specified, child description must match too
        @return:        The wrapped child object
        @rtype:         L{BlitzObjectWrapper}
        """
        for c in self.listChildren():
            if c.getName() == name:
                if description is None or omero_type(description) == omero_type(c.getDescription()):
                    return c
        return None

    def getDetails (self):
        """
        Gets the details of the wrapped object
        
        @return:    L{omero.gateway.DetailsWrapper} or None if object not loaded
        @rtype:     L{DetailsWrapper}
        """
        if self._obj.loaded:
            return omero.gateway.DetailsWrapper (self._conn, self._obj.getDetails())
        return None
    
    
    def getDate(self):
        """
        Returns the object's acquisitionDate, or creation date (details.creationEvent.time)
        
        @return:    A L{datetime.datetime} object 
        @rtype:     datetime
        """
        
        try:
            if self._obj.acquisitionDate.val is not None and self._obj.acquisitionDate.val > 0:
                t = self._obj.acquisitionDate.val
                return datetime.fromtimestamp(t/1000)
        except:
            # object doesn't have acquisitionDate
            pass
        
        return self.creationEventDate()
    
    
    def save (self):
        """ 
        Uses the updateService to save the wrapped object.
        
        @rtype:     None
        """
        self._obj = self._conn.getUpdateService().saveAndReturnObject(self._obj)

    def saveAs (self, details):
        """ 
        Save this object, keeping the object owner the same as the one on provided details 
        If the current user is an admin but is NOT the owner specified in 'details',
        then create a new connection for that owner, clone the current object under that
        connection and save. 
        Otherwise, simply save. 
        
        @param details:     The Details specifying owner to save to
        @type details:      L{DetailsWrapper}
        @return:            None
        """
        if self._conn.isAdmin():
            d = self.getDetails()
            if d.getOwner() and \
                    d.getOwner().omeName == details.getOwner().omeName and \
                    d.getGroup().name == details.getGroup().name:
                return self.save()
            else:
                newConn = self._conn.suConn(details.getOwner().omeName, details.getGroup().name)
                #p = omero.sys.Principal()
                #p.name = details.getOwner().omeName
                #p.group = details.getGroup().name
                #p.eventType = "User"
                #newConnId = self._conn.getSessionService().createSessionWithTimeout(p, 60000)
                #newConn = self._conn.clone()
                #newConn.connect(sUuid=newConnId.getUuid().val)
            clone = self.__class__(newConn, self._obj)
            clone.save()
            self._obj = clone._obj
            return
        else:
            return self.save()

    def canWrite (self):
        """ 
        Delegates to the connection L{BlitzGateway.canWrite} method
        
        @rtype:     Boolean
        """
        return self._conn.canWrite(self._obj)

    def canOwnerWrite (self):
        """
        Returns isUserWrite() from the object's permissions
        
        @rtype:     Boolean
        @return:    True if the objects's permissions allow user to write
        """
        return self._obj.details.permissions.isUserWrite()
    
    def canDelete(self):
        """
        Determines whether the current user can delete this object.
        Returns True if the object L{isOwned} by the current user or L{isLeaded}
        (current user is leader of this the group that this object belongs to)
        
        @rtype:     Boolean
        @return:    see above
        """
        return self.isOwned() or self.isLeaded()
    
    def isOwned(self):
        """
        Returns True if the object owner is the same user specified in the connection's Event Context
        
        @rtype:     Boolean
        @return:    True if current user owns this object
        """
        return (self._obj.details.owner.id.val == self._conn.getEventContext().userId)
    
    def isLeaded(self):
        """
        Returns True if the group that this object belongs to is lead by the currently logged-in user
        
        @rtype:     Boolean
        @return:    see above
        """
        if self._obj.details.group.id.val in self._conn.getEventContext().leaderOfGroups:
            return True
        return False
    
    def isEditable(self):
        """
        Determines whether the current user can edit this object. 
        Returns True if the object L{isOwned} by the current user
        Also True if object is not L{private<isPrivate>} AND not L{readOnly<isReadOnly>}
        
        @rtype:     Boolean
        @return:    see above
        """
        return self.isOwned() or (not self.isPrivate() and not self.isReadOnly())
    
    def isPublic(self):
        """
        Determines if the object permissions are world readable, ie permissions.isWorldRead()
        
        @rtype:     Boolean
        @return:    see above
        """
        return self._obj.details.permissions.isWorldRead()
    
    def isShared(self):
        """
        Determines if the object is sharable between groups (but not public) 
        
        @rtype:     Boolean
        @return:    True if the object is not L{public<isPublic>} AND the 
                    object permissions allow group read.
        """
        if not self.isPublic():
            return self._obj.details.permissions.isGroupRead()
        return False
    
    def isPrivate(self):
        """
        Determines if the object is private
        
        @rtype:     Boolean
        @return:    True if the object is not L{public<isPublic>} and not L{shared<isShared>} and 
                    permissions allow user to read.
        """
        if not self.isPublic() and not self.isShared():
            return self._obj.details.permissions.isUserRead()
        return False
    
    def isReadOnly(self):
        """
        Determines if the object is visible but not writeable
        
        @rtype:     Boolean
        @return:    True if public but not world writable
                    True if shared but not group writable
                    True if private but not user writable
        """
        if self.isPublic() and not self._obj.details.permissions.isWorldWrite():
            return True
        elif self.isShared() and not self._obj.details.permissions.isGroupWrite():
            return True
        elif self.isPrivate() and not self._obj.details.permissions.isUserWrite():
            return True
        return False
    
    def countChildren (self):
        """
        Counts available number of child objects.
        
        @return:    The number of child objects available
        @rtype:     Long
        """
        
        childw = self._getChildWrapper()
        klass = "%sLinks" % childw().OMERO_CLASS.lower()
        #self._cached_countChildren = len(self._conn.getQueryService().findAllByQuery("from %s as c where c.parent.id=%i" % (self.LINK_CLASS, self._oid), None))
        self._cached_countChildren = self._conn.getContainerService().getCollectionCount(self.OMERO_CLASS, klass, [self._oid], None)[self._oid]
        return self._cached_countChildren

    def countChildren_cached (self):
        """
        countChildren, but caching the first result, useful if you need to call this multiple times in
        a single sequence, but have no way of storing the value between them.
        It is actually a hack to support django template's lack of break in for loops
        
        @return:    The number of child objects available
        @rtype:     Long
        """
        
        if not hasattr(self, '_cached_countChildren'):
            return self.countChildren()
        return self._cached_countChildren

    def listChildren (self, ns=None, val=None, params=None):
        """
        Lists available child objects.

        @rtype: generator of L{BlitzObjectWrapper} objs
        @return: child objects.
        """
        childw = self._getChildWrapper()
        klass = childw().OMERO_CLASS
        if not params:
            params = omero.sys.Parameters()
        if not params.map:
            params.map = {}
        params.map["dsid"] = omero_type(self._oid)
        query = "select c from %s as c" % self.LINK_CLASS
        if ns is not None:
            params.map["ns"] = omero_type(ns)
        query += """ join fetch c.child as ch
                     left outer join fetch ch.annotationLinks as ial
                     left outer join fetch ial.child as a """
        query += " where c.parent.id=:dsid"
        if ns is not None:
            query += " and a.ns=:ns"
            if val is not None:
                if isinstance(val, StringTypes):
                    params.map["val"] = omero_type(val)
                    query +=" and a.textValue=:val"
        query += " order by c.child.name"
        childnodes = [ x.child for x in self._conn.getQueryService().findAllByQuery(query, params)]
        for child in childnodes:
            yield childw(self._conn, child, self._cache)

    def getParent (self, withlinks=False):
        """
        List a single parent, if available.

        While the model suports many to many relationships between most objects, there are
        implementations that assume a single project per dataset, a single dataset per image,
        etc. This is just a shortcut method to return a single parent object.

        @type withlinks: Boolean
        @param withlinks: if true result will be a tuple of (linkobj, obj)
        @rtype: L{BlitzObjectWrapper} ( or tuple(L{BlitzObjectWrapper}, L{BlitzObjectWrapper}) )
        @return: the parent object with or without the link depending on args
        """

        rv = self.listParents(withlinks=withlinks)
        return len(rv) and rv[0] or None

    def listParents (self, withlinks=False):
        """
        Lists available parent objects.

        @type withlinks: Boolean
        @param withlinks: if true each yielded result will be a tuple of (linkobj, obj)
        @rtype: list of L{BlitzObjectWrapper} ( or tuple(L{BlitzObjectWrapper}, L{BlitzObjectWrapper}) )
        @return: the parent objects, with or without the links depending on args
        """
        if self.PARENT_WRAPPER_CLASS is None:
            return ()
        parentw = self._getParentWrapper()
        param = omero.sys.Parameters() # TODO: What can I use this for?
        if withlinks:
            parentnodes = [ (parentw(self._conn, x.parent, self._cache), BlitzObjectWrapper(self._conn, x)) for x in self._conn.getQueryService().findAllByQuery("from %s as c where c.child.id=%i" % (parentw().LINK_CLASS, self._oid), param)]
        else:
            parentnodes = [ parentw(self._conn, x.parent, self._cache) for x in self._conn.getQueryService().findAllByQuery("from %s as c where c.child.id=%i" % (parentw().LINK_CLASS, self._oid), param)]
        return parentnodes

    def getAncestry (self):
        """
        Get a list of Ancestors. First in list is parent of this object. 
        TODO: Assumes getParent() returns a single parent. 
        
        @rtype: List of L{BlitzObjectWrapper}
        @return:    List of Ancestor objects
        """
        rv = []
        p = self.getParent()
        while p:
            rv.append(p)
            p = p.getParent()
        return rv
    
    def getParentLinks(self, pids=None):
        """
        Get a list of parent objects links. 
        
        @param pids:    List of parent IDs
        @type pids:     L{Long}
        @rtype:         List of L{BlitzObjectWrapper}
        @return:        List of parent object links
        """
        
        if self.PARENT_WRAPPER_CLASS is None:
            raise AttributeError("This object has no parent objects")
        parentw = self._getParentWrapper()
        query_serv = self._conn.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["child"] = rlong(self.id)                    
        sql = "select pchl from %s as pchl " \
                "left outer join fetch pchl.parent as parent " \
                "left outer join fetch pchl.child as child " \
                "where child.id=:child" % parentw().LINK_CLASS
        if isinstance(pids, list) and len(pids) > 0:
            p.map["parent"] = rlist([rlong(pa) for pa in pids])
            sql+=" and parent.id in (:parent)"
        for pchl in query_serv.findAllByQuery(sql, p):
            yield BlitzObjectWrapper(self, pchl) 
        
    def getChildLinks(self, chids=None):
        """
        Get a list of child objects links. 
        
        @param chids:   List of children IDs
        @type chids:    L{Long}
        @rtype:         List of L{BlitzObjectWrapper}
        @return:        List of child object links
        """
        
        if self.CHILD_WRAPPER_CLASS is None:
            raise AttributeError("This object has no child objects")
        childw = self._getChildWrapper()
        query_serv = self._conn.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["parent"] = rlong(self.id)                    
        sql = "select pchl from %s as pchl left outer join fetch pchl.child as child \
                left outer join fetch pchl.parent as parent where parent.id=:parent" % self.LINK_CLASS
        if isinstance(chids, list) and len(chids) > 0:
            p.map["children"] = rlist([rlong(ch) for ch in chids])
            sql+=" and child.id in (:children)"
        for pchl in query_serv.findAllByQuery(sql, p):
            yield BlitzObjectWrapper(self, pchl)       

    def _loadAnnotationLinks (self):
        """ Loads the annotation links for the object (if not already loaded) and saves them to the object """
        if not hasattr(self._obj, 'isAnnotationLinksLoaded'): #pragma: no cover
            raise NotImplementedError
        if not self._obj.isAnnotationLinksLoaded():
            query = "select l from %sAnnotationLink as l join fetch l.details.owner join fetch l.details.creationEvent "\
            "join fetch l.child as a join fetch a.details.owner join fetch a.details.creationEvent "\
            "where l.parent.id=%i" % (self.OMERO_CLASS, self._oid)
            links = self._conn.getQueryService().findAllByQuery(query, None)
            self._obj._annotationLinksLoaded = True
            self._obj._annotationLinksSeq = links

    # _listAnnotationLinks
    def _getAnnotationLinks (self, ns=None):
        """
        Checks links are loaded and returns a list of Annotation Links filtered by 
        namespace if specified
        
        @param ns:  Namespace
        @type ns:   String
        @return:    List of Annotation Links on this object 
        @rtype:     List of Annotation Links
        """
        self._loadAnnotationLinks()
        rv = self.copyAnnotationLinks()
        if ns is not None:
            rv = filter(lambda x: x.getChild().getNs() and x.getChild().getNs().val == ns, rv)
        return rv


    def unlinkAnnotations (self, ns):
        """
        Uses updateService to unlink annotations, with specified ns
        
        @param ns:      Namespace
        @type ns:       String
        """
        for al in self._getAnnotationLinks(ns=ns):
            update = self._conn.getUpdateService()
            update.deleteObject(al)
        self._obj.unloadAnnotationLinks()        

    def removeAnnotations (self, ns):
        """
        Uses updateService to delete annotations, with specified ns, and their links on the object
        
        @param ns:      Namespace
        @type ns:       String
        """
        for al in self._getAnnotationLinks(ns=ns):
            a = al.child
            update = self._conn.getUpdateService()
            update.deleteObject(al)
            update.deleteObject(a)
        self._obj.unloadAnnotationLinks()        
    
    # findAnnotations(self, ns=[])
    def getAnnotation (self, ns=None):
        """
        Gets the first annotation on the object, filtered by ns if specified
        
        @param ns:      Namespace
        @type ns:       String
        @return:        L{AnnotationWrapper} or None
        """
        rv = self._getAnnotationLinks(ns)
        if len(rv):
            return AnnotationWrapper._wrap(self._conn, rv[0].child, link=rv[0])
        return None

    def listAnnotations (self, ns=None):
        """
        List annotations in the ns namespace, linked to this object
        
        @return:    Generator yielding L{AnnotationWrapper}
        @rtype:     L{AnnotationWrapper} generator
        """
        for ann in self._getAnnotationLinks(ns):
            yield AnnotationWrapper._wrap(self._conn, ann.child, link=ann)
    
    def listOrphanedAnnotations(self, eid=None, ns=None, anntype=None):
        """
        Retrieve all Annotations not linked to the given Project, Dataset, Image,
        Screen, Plate, Well ID controlled by the security system. 
        
        @param o_type:      type of Object
        @type o_type:       String
        @param oid:         Object ID
        @type oid:          Long
        @return:            Generator yielding Tags
        @rtype:             L{AnnotationWrapper} generator
        """
        
        if anntype is not None:
            if anntype.title() not in ('Text', 'Tag', 'File', 'Long', 'Boolean'):
                raise AttributeError('It only retrieves: Text, Tag, File, Long, Boolean')
            sql = "select an from %sAnnotation as an " % anntype.title()
        else:
            sql = "select an from Annotation as an " \
        
        sql += "where not exists ( select obal from %sAnnotationLink as obal "\
                "where obal.child=an.id and obal.parent.id=:oid) " % self.OMERO_CLASS
        
        q = self._conn.getQueryService()                
        p = omero.sys.Parameters()
        p.map = {}
        p.map["oid"] = rlong(self._oid)
        if ns is None:            
            sql += " and an.ns is null"
        else:
            p.map["ns"] = rlist([rstring(n) for n in ns])
            sql += " and (an.ns not in (:ns) or an.ns is null)"        
        if eid is not None:
            sql += " and an.details.owner.id=:eid"
            p.map["eid"] = rlong(eid)
 
        for e in q.findAllByQuery(sql,p):
            yield AnnotationWrapper._wrap(self._conn, e)
    
    def _linkAnnotation (self, ann):
        """
        Saves the annotation to DB if needed - setting the permissions manually.
        Creates the annotation link and saves it, setting permissions manually.
        TODO: Can't set permissions manually in 4.2 - Assumes world & group writable
        
        @param ann:     The annotation object
        @type ann:      L{AnnotationWrapper}
        """
        if not ann.getId():
            # Not yet in db, save it
            ann = ann.__class__(self._conn, self._conn.getUpdateService().saveAndReturnObject(ann._obj))
        #else:
        #    ann.save()
        lnktype = "%sAnnotationLinkI" % self.OMERO_CLASS
        lnk = getattr(omero.model, lnktype)()
        lnk.setParent(self._obj.__class__(self._obj.id, False))
        lnk.setChild(ann._obj.__class__(ann._obj.id, False))
        self._conn.getUpdateService().saveObject(lnk)
        return ann


    def linkAnnotation (self, ann, sameOwner=True):
        """
        Link the annotation to this object.
        
        @param ann:         The Annotation object
        @type ann:          L{AnnotationWrapper}
        @param sameOwner:   If True, try to make sure that the link is created by the object owner
        @type sameOwner:    Boolean
        @return:            The annotation
        @rtype:             L{AnnotationWrapper}
        """
        
        """
        My notes (will) to try and work out what's going on! 
        If sameOwner:
            if current user is admin AND they are not the object owner,
                if the object owner and annotation owner are the same:
                    use the Annotation connection to do the linking
                else use a new connection for the object owner (?same owner as ann?)
                do linking
            else:
                try to switch the current group of this object to the group of the annotation - do linking
        else - just do linking
        
        """
        if sameOwner:
            d = self.getDetails()
            ad = ann.getDetails()
            if self._conn.isAdmin() and self._conn._userid != d.getOwner().id:
                # Keep the annotation owner the same as the linked of object's
                if ad.getOwner() and d.getOwner().omeName == ad.getOwner().omeName and d.getGroup().name == ad.getGroup().name:
                    newConn = ann._conn
                else:
                    #p = omero.sys.Principal()
                    #p.name = d.getOwner().omeName
                    group = None
                    if d.getGroup():
                        group = d.getGroup().name
                    # TODO: Do you know that the object owner is same as ann owner??
                    newConn = self._conn.suConn(d.getOwner().omeName, group)
                    #p.eventType = "User"
                    #newConnId = self._conn.getSessionService().createSessionWithTimeout(p, 60000)
                    #newConn = self._conn.clone()
                    #newConn.connect(sUuid=newConnId.getUuid().val)
                clone = self.__class__(newConn, self._obj)
                ann = clone._linkAnnotation(ann)
                if newConn != self._conn:
                    newConn.seppuku()
            elif d.getGroup():
                # Try to match group
                # TODO: Should switch session of this object to use group from annotation (ad) not this object (d) ?
                self._conn.setGroupForSession(d.getGroup().getId())
                ann = self._linkAnnotation(ann)
                self._conn.revertGroupForSession()
            else:
                ann = self._linkAnnotation(ann)
        else:
            ann = self._linkAnnotation(ann)
        self.unloadAnnotationLinks()
        return ann


    def simpleMarshal (self, xtra=None, parents=False):
        """
        Creates a dict representation of this object.
        E.g. for Image: {'description': '', 'author': 'Will Moore', 'date': 1286332557.0,
            'type': 'Image', 'id': 3841L, 'name': 'cb_4_w500_t03_z01.tif'}
        
        @param xtra:        A dict of extra keys to include. E.g. 'childCount'
        @type xtra:         Dict
        @param parents:     If True, include a list of ancestors (in simpleMarshal form) as 'parents'
        @type parents:      Boolean
        @return:            A dict representation of this object
        @rtype:             Dict
        """
        rv = {'type': self.OMERO_CLASS,
              'id': self.getId(),
              'name': self.getName(),
              'description': self.getDescription(),
              }
        if hasattr(self, '_attrs'):
            # 'key' -> key = _obj[key]
            # '#key' -> key = _obj[key].value.val
            # 'key;title' -> title = _obj[key]
            # 'key|wrapper' -> key = omero.gateway.wrapper(_obj[key]).simpleMarshal
            for k in self._attrs:
                if ';' in k:
                    s = k.split(';')
                    k = s[0]
                    rk = ';'.join(s[1:])
                else:
                    rk = k
                rk = rk.replace('#', '')
                if '|' in k:
                    s = k.split('|')
                    k2 = s[0]
                    w = '|'.join(s[1:])
                    if rk == k:
                        rk = k2
                    k = k2
                    v = getattr(self, k)
                    if v is not None:
                        v = getattr(omero.gateway, w)(self._conn, v).simpleMarshal()
                else:
                    if k.startswith('#'):
                        v = getattr(self, k[1:])
                        if v is not None:
                            v = v._value
                    else:
                        v = getattr(self, k)
                    if hasattr(v, 'val'):
                        v = v.val
                rv[rk] = v
        if xtra: # TODO check if this can be moved to a more specific place
            if xtra.has_key('childCount'):
                rv['child_count'] = self.countChildren()
        if parents:
            rv['parents'] = map(lambda x: x.simpleMarshal(), self.getAncestry())
        return rv

    #def __str__ (self):
    #    if hasattr(self._obj, 'value'):
    #        return str(self.value)
    #    return str(self._obj)

    def __getattr__ (self, attr):
        """
        Attempts to return the named attribute of this object. E.g. image.__getattr__('name') or 'getName'
        In cases where the attribute E.g. 'getImmersion' should return an enumeration, this is specified by the
        attr name starting with '#' #immersion.
        In cases where the attribute E.g. 'getLightSource' should return a wrapped object, this is handled
        by the parent encoding the wrapper in the attribute name. E.g 'lightSource|LightSourceWrapper'
        In both cases this returns a method that will return the object.
        In addition, lookup of methods that return an rtype are wrapped to the method instead returns a primitive type.
        E.g. image.getArchived() will return a boolean instead of rbool.

        @param attr:    The name of the attribute to get
        @type attr:     String
        @return:        The named attribute.
        @rtype:         method, value (string, long etc)
        """

        # handle lookup of 'get' methods, using '_attrs' dict to define how we wrap returned objects. 
        if attr != 'get' and attr.startswith('get') and hasattr(self, '_attrs'):
            tattr = attr[3].lower() + attr[4:]      # 'getName' -> 'name'
            attrs = filter(lambda x: tattr in x, self._attrs)   # find attr with 'name'
            for a in attrs:
                if a.startswith('#') and a[1:] == tattr:
                    v = getattr(self, tattr)
                    if v is not None:
                        v = v._value
                    def wrap ():
                        return v
                    return wrap
                if len(a) > len(tattr) and a[len(tattr)] == '|':        # E.g.  a = lightSource|LightSourceWrapper
                    def wrap ():                                # E.g. method returns a LightSourceWrapper(omero.model.lightSource)
                        return getattr(omero.gateway, a[len(tattr)+1:])(self._conn, getattr(self, tattr))
                    return wrap

        # handle lookup of 'get' methods when we don't have '_attrs' on the object, E.g. image.getAcquisitionDate
        if attr != 'get' and attr.startswith('get'):
            attrName = attr[3].lower() + attr[4:]   # E.g. getAcquisitionDate -> acquisitionDate
            if hasattr(self._obj, attrName):
                def wrap():
                    rv = getattr(self._obj, attrName)
                    if hasattr(rv, 'val'):
                        return isinstance(rv.val, StringType) and rv.val.decode('utf8') or rv.val
                    elif isinstance(rv, omero.model.IObject):
                        return BlitzObjectWrapper(self._conn, rv)
                    return rv
                return wrap

        # handle direct access of attributes. E.g. image.acquisitionDate
        # also handles access to other methods E.g. image.unloadPixels()
        if not hasattr(self._obj, attr) and hasattr(self._obj, '_'+attr):
            attr = '_' + attr
        if hasattr(self._obj, attr):
            rv = getattr(self._obj, attr)
            if hasattr(rv, 'val'):   # unwrap rtypes
                return isinstance(rv.val, StringType) and rv.val.decode('utf8') or rv.val
            return rv
        raise AttributeError("'%s' object has no attribute '%s'" % (self._obj.__class__.__name__, attr))


    # some methods are accessors in _obj and return and omero:: type. The obvious ones we wrap to return a python type
    
    def getId (self):
        """
        Gets this object ID
        
        @return: Long or None
        """
        oid = self._obj.getId()
        if oid is not None:
            return oid.val
        return None

    def getName (self):
        """
        Gets this object name
        
        @return: String or None
        """
        if hasattr(self._obj, 'name'):
            if hasattr(self._obj.name, 'val'):
                return self._obj.getName().val
            else:
                return self._obj.getName()
        else:
            return None

    def getDescription (self):
        """
        Gets this object description
        
        @return: String
        """
        rv = hasattr(self._obj, 'description') and self._obj.getDescription() or None
        return rv and rv.val or ''

    def getOwner (self):
        """
        Gets user who is the owner of this object.
        
        @return: _ExperimenterWrapper
        """
        return self.getDetails().getOwner()

    def getOwnerFullName (self):
        """
        Gets full name of the owner of this object.
        
        @return: String or None
        """
        try:
            lastName = self.getDetails().getOwner().lastName
            firstName = self.getDetails().getOwner().firstName
            middleName = self.getDetails().getOwner().middleName
            
            if middleName is not None and middleName != '':
                name = "%s %s. %s" % (firstName, middleName, lastName)
            else:
                name = "%s %s" % (firstName, lastName)
            return name
        except:
            logger.error(traceback.format_exc())
            return None

    def getOwnerOmeName (self):
        """
        Gets omeName of the owner of this object.
        
        @return: String
        """
        return self.getDetails().getOwner().omeName

    
    def creationEventDate(self):
        """
        Gets event time in timestamp format (yyyy-mm-dd hh:mm:ss.fffffff) when object was created.
        
        @return:    The datetime for object creation
        @rtype:     datetime.datetime
        """
        
        if self._creationDate is not None:
            return datetime.fromtimestamp(self._creationDate/1000)
            
        try:
            if self._obj.details.creationEvent._time is not None:
                self._creationDate = self._obj.details.creationEvent._time.val
            else:
                self._creationDate = self._conn.getQueryService().get("Event", self._obj.details.creationEvent.id.val).time.val
        except:
            self._creationDate = self._conn.getQueryService().get("Event", self._obj.details.creationEvent.id.val).time.val
        return datetime.fromtimestamp(self._creationDate/1000)
        

    def updateEventDate(self):
        """
        Gets event time in timestamp format (yyyy-mm-dd hh:mm:ss.fffffff) when object was updated.
        
        @return:    The datetime for object update
        @rtype:     datetime.datetime
        """
        
        try:
            if self._obj.details.updateEvent.time is not None:
                t = self._obj.details.updateEvent.time.val
            else:
                t = self._conn.getQueryService().get("Event", self._obj.details.updateEvent.id.val).time.val
        except:
            t = self._conn.getQueryService().get("Event", self._obj.details.updateEvent.id.val).time.val
        return datetime.fromtimestamp(t/1000)


    # setters are also provided
    
    def setName (self, value):
        """
        Sets the name of the object
        
        @param value:   New name
        @type value:    String
        """
        self._obj.setName(omero_type(value))

    def setDescription (self, value):
        """
        Sets the description of the object
        
        @param value:   New description
        @type value:    String
        """
        self._obj.setDescription(omero_type(value))

## BASIC ##

class NoProxies (object):
    """ A dummy placeholder to indicate that proxies haven't been created """
    def __getitem__ (self, k):
        raise Ice.ConnectionLostException

class _BlitzGateway (object):
    """
    Connection wrapper. Handles connecting and keeping the session alive, creation of various services,
    context switching, security privilidges etc.  
    """
    
    CONFIG = {}
    """
    Holder for class wide configuration properties:
     - IMG_RDEFNS:  a namespace for annotations linked on images holding the default rendering
                    settings object id.
     - IMG_ROPTSNS: a namespace for annotations linked on images holding default rendering options
                    that don't get saved in the rendering settings.
    One good place to define this is on the extending class' connect() method.
    """
    ICE_CONFIG = None
    """
    ICE_CONFIG - Defines the path to the Ice configuration
    """
#    def __init__ (self, username, passwd, server, port, client_obj=None, group=None, clone=False):
    
    def __init__ (self, username=None, passwd=None, client_obj=None, group=None, clone=False, try_super=False, host=None, port=None, extra_config=None, secure=False, anonymous=True, useragent=None):
        """
        Create the connection wrapper. Does not attempt to connect at this stage
        Initialises the omero.client
        
        @param username:    User name. If not specified, use 'omero.gateway.anon_user'
        @type username:     String
        @param passwd:      Password.
        @type passwd:       String
        @param client_obj:  omero.client
        @param group:       name of group to try to connect to
        @type group:        String
        @param clone:       If True, overwrite anonymous with False
        @type clone:        Boolean
        @param try_super:   Try to log on as super user ('system' group) 
        @type try_super:    Boolean
        @param host:        Omero server host. 
        @type host:         String
        @param port:        Omero server port. 
        @type port:         Integer
        @param extra_config:    Dictionary of extra configuration
        @type extra_config:     Dict
        @param secure:      Initial underlying omero.client connection type (True=SSL/False=insecure)
        @type secure:       Boolean
        @param anonymous:   
        @type anonymous:    Boolean
        @param useragent:   Log which python clients use this connection. E.g. 'OMERO.webadmin'
        @type useragent:    String
        """

        if extra_config is None: extra_config = []
        super(_BlitzGateway, self).__init__()
        self.c = client_obj
        if not type(extra_config) in (type(()), type([])):
            extra_config=[extra_config]
        self.extra_config = extra_config
        self.ice_config = [self.ICE_CONFIG]
        self.ice_config.extend(extra_config)
        self.ice_config = map(lambda x: str(x), filter(None, self.ice_config))

        self.host = host
        self.port = port
        self.secure = secure
        self.useragent = useragent

        self._sessionUuid = None
        self._session_cb = None
        self._session = None
        self._lastGroupId = None
        self._anonymous = anonymous

        self._connected = False
        self._user = None
        self._userid = None
        self._proxies = NoProxies()
        if self.c is None:
            self._resetOmeroClient()
        else:
            # if we already have client initialised, we can go ahead and create our services.
            self._connected = True
            self._createProxies()
        if not username:
            username = self.c.ic.getProperties().getProperty('omero.gateway.anon_user')
            passwd = self.c.ic.getProperties().getProperty('omero.gateway.anon_pass')
        #logger.debug('super: %s %s %s' % (try_super, str(group), self.c.ic.getProperties().getProperty('omero.gateway.admin_group')))
        if try_super:
            self.group = 'system' #self.c.ic.getProperties().getProperty('omero.gateway.admin_group')
        else:
            self.group = group and group or None

        # The properties we are setting through the interface
        self.setIdentity(username, passwd, not clone)

    def isAnonymous (self):
        """ 
        Returns the anonymous flag 
        
        @return:    Anonymous
        @rtype:     Boolean
        """
        return not not self._anonymous

    def getProperty(self, k):
        """
        Returns named property of the wrapped omero.client
        
        @return:    named client property
        """
        return self.c.getProperty(k)

    def clone (self):
        """
        Returns a new instance of this class, with all matching properties. 
        TODO: Add anonymous and userAgent parameters?
        
        @return:    Clone of this connection wrapper
        @rtype:     L{_BlitzGateway}
        """
        return self.__class__(self._ic_props[omero.constants.USERNAME],
                              self._ic_props[omero.constants.PASSWORD],
                              host = self.host,
                              port = self.port,
                              extra_config=self.extra_config,
                              clone=True,
                              secure=self.secure,
                              anonymous=self._anonymous, 
                              useragent=self.useragent)
                              #self.server, self.port, clone=True)

    def setIdentity (self, username, passwd, _internal=False):
        """
        Saves the username and password for later use, creating session etc
        
        @param username:    User name. 
        @type username:     String
        @param passwd:      Password.
        @type passwd:       String
        @param _internal:   If False, set _anonymous = False
        @type _internal:    Booelan
        """
        self._ic_props = {omero.constants.USERNAME: username,
                          omero.constants.PASSWORD: passwd}
        if not _internal:
            self._anonymous = False
    
    def suConn (self, username, group=None, ttl=60000):
        """
        If current user isAdmin, return new connection owned by 'username'
        
        @param username:    Username for new connection
        @type username:     String
        @param group:       If specified, try to log in to this group
        @type group:        String
        @param ttl:         Timeout for new session
        @type ttl:          Int
        @return:            Clone of this connection, with username's new Session
        @rtype:             L{_BlitzGateway} or None if not admin or username unknown
        """
        if self.isAdmin():
            if group is None:
                e = self.findExperimenter(username)
                if e is None:
                    return
                group = e._obj._groupExperimenterMapSeq[0].parent.name.val
            p = omero.sys.Principal()
            p.name = username
            p.group = group
            p.eventType = "User"
            newConnId = self.getSessionService().createSessionWithTimeout(p, ttl)
            newConn = self.clone()
            newConn.connect(sUuid=newConnId.getUuid().val)
            return newConn

    def keepAlive (self):
        """
        Keeps service alive. 
        Returns True if connected. If connection was lost, reconnecting.
        If connection failed, returns False and error is logged. 
        
        @return:    True if connection alive. 
        @rtype:     Boolean
        """
        
        try:
            if self.c.sf is None: #pragma: no cover
                logger.debug('... c.sf is None, reconnecting')
                return self.connect()
            return self.c.sf.keepAlive(self._proxies['admin']._obj)
        except Ice.ObjectNotExistException: #pragma: no cover
            # The connection is there, but it has been reset, because the proxy no longer exists...
            logger.debug(traceback.format_exc())
            logger.debug("... reset, not reconnecting")
            return False
        except Ice.ConnectionLostException: #pragma: no cover
            # The connection was lost. This shouldn't happen, as we keep pinging it, but does so...
            logger.debug(traceback.format_exc())
            logger.debug("... lost, reconnecting")
            #return self.connect()
            return False
        except Ice.ConnectionRefusedException: #pragma: no cover
            # The connection was refused. We lost contact with glacier2router...
            logger.debug(traceback.format_exc())
            logger.debug("... refused, not reconnecting")
            return False
        except omero.SessionTimeoutException: #pragma: no cover
           # The connection is there, but it has been reset, because the proxy no longer exists...
           logger.debug(traceback.format_exc())
           logger.debug("... reset, not reconnecting")
           return False
        except omero.RemovedSessionException: #pragma: no cover
            # Session died on us
            logger.debug(traceback.format_exc())
            logger.debug("... session has left the building, not reconnecting")
            return False
        except Ice.UnknownException, x: #pragma: no cover
            # Probably a wrapped RemovedSession
            logger.debug(traceback.format_exc())
            logger.debug('Ice.UnknownException: %s' % str(x))
            logger.debug("... ice says something bad happened, not reconnecting")
            return False
        except:
            # Something else happened
            logger.debug(traceback.format_exc())
            logger.debug("... error not reconnecting")
            return False

    def seppuku (self, softclose=False): #pragma: no cover
        """
        Terminates connection with killSession(). If softclose is False, the session is really
        terminate disregarding its connection refcount. 

        @param softclose:   Boolean
        """
        self._connected = False
        if softclose:
            try:
                r = self.c.sf.getSessionService().getReferenceCount(self._sessionUuid)
                self.c.closeSession()
                if r < 2:
                    self._session_cb and self._session_cb.close(self)
            except Ice.OperationNotExistException:
                self.c.closeSession()
        else:
            self._closeSession()
        self._proxies = NoProxies()
        logger.info("closed connecion (uuid=%s)" % str(self._sessionUuid))

#    def __del__ (self):
#        logger.debug("##GARBAGE COLLECTOR KICK IN")
    
    def _createProxies (self):
        """
        Creates proxies to the server services. Called on connection or security switch.
        Doesn't actually create any services themselves. Created if/when needed. 
        If proxies have been created already, they are resynced and reused. 
        """
        
        if not isinstance(self._proxies, NoProxies):
            logger.debug("## Reusing proxies")
            for k, p in self._proxies.items():
                p._resyncConn(self)
        else:
            logger.debug("## Creating proxies")
            self._proxies = {}
            self._proxies['admin'] = ProxyObjectWrapper(self, 'getAdminService')
            self._proxies['config'] = ProxyObjectWrapper(self, 'getConfigService')
            self._proxies['container'] = ProxyObjectWrapper(self, 'getContainerService')
            self._proxies['delete'] = ProxyObjectWrapper(self, 'getDeleteService')
            self._proxies['export'] = ProxyObjectWrapper(self, 'createExporter')
            self._proxies['ldap'] = ProxyObjectWrapper(self, 'getLdapService')
            self._proxies['metadata'] = ProxyObjectWrapper(self, 'getMetadataService')
            self._proxies['query'] = ProxyObjectWrapper(self, 'getQueryService')
            self._proxies['pixel'] = ProxyObjectWrapper(self, 'getPixelsService')
            self._proxies['projection'] = ProxyObjectWrapper(self, 'getProjectionService')
            self._proxies['rawpixels'] = ProxyObjectWrapper(self, 'createRawPixelsStore')
            self._proxies['rendering'] = ProxyObjectWrapper(self, 'createRenderingEngine')
            self._proxies['rendsettings'] = ProxyObjectWrapper(self, 'getRenderingSettingsService')
            self._proxies['thumbs'] = ProxyObjectWrapper(self, 'createThumbnailStore')
            self._proxies['rawfile'] = ProxyObjectWrapper(self, 'createRawFileStore')
            self._proxies['repository'] = ProxyObjectWrapper(self, 'getRepositoryInfoService')
            self._proxies['roi'] = ProxyObjectWrapper(self, 'getRoiService')
            self._proxies['script'] = ProxyObjectWrapper(self, 'getScriptService')
            self._proxies['search'] = ProxyObjectWrapper(self, 'createSearchService')
            self._proxies['session'] = ProxyObjectWrapper(self, 'getSessionService')
            self._proxies['share'] = ProxyObjectWrapper(self, 'getShareService')
            self._proxies['timeline'] = ProxyObjectWrapper(self, 'getTimelineService')
            self._proxies['types'] = ProxyObjectWrapper(self, 'getTypesService')
            self._proxies['update'] = ProxyObjectWrapper(self, 'getUpdateService')
        self._ctx = self._proxies['admin'].getEventContext()
        if self._ctx is not None:
            self._userid = self._ctx.userId
            # "guest" user has no access that method.
            self._user = self._ctx.userName!="guest" and self.getExperimenter(self._userid) or None
        else:
            self._userid = None
            self._user = None

        if self._session_cb: #pragma: no cover
            if self._was_join:
                self._session_cb.join(self)
            else:
                self._session_cb.create(self)

    def setSecure (self, secure=True):
        """ 
        Switches between SSL and insecure (faster) connections to Blitz.
        The gateway must already be connected.
        
        @param secure:  If False, use an insecure connection
        @type secure:   Boolean
        """
        if hasattr(self.c, 'createClient') and (secure ^ self.c.isSecure()):
            oldC = self.c
            self.c = oldC.createClient(secure=secure)
            oldC.__del__() # only needs to be called if previous doesn't throw
            self.c = self.c.createClient(secure=secure)
            self._createProxies()
            self.secure = secure

    def isSecure (self):
        """ Returns 'True' if the underlying omero.clients.BaseClient is connected using SSL """
        return hasattr(self.c, 'isSecure') and self.c.isSecure() or False

    def _getSessionId (self):
        return self.c.getSessionId()

    def _createSession (self):
        """
        Creates a new session for the principal given in the constructor.
        Used during L{connect} method
        """
        s = self.c.createSession(self._ic_props[omero.constants.USERNAME],
                                 self._ic_props[omero.constants.PASSWORD])
        self._sessionUuid = self._getSessionId()
        ss = self.c.sf.getSessionService()
        self._session = ss.getSession(self._sessionUuid)
        self._lastGroupId = None
        s.detachOnDestroy()
        self._was_join = False
        if self.group is not None:
            # try something that fails if the user don't have permissions on the group
            self.c.sf.getAdminService().getEventContext()
        self.setSecure(self.secure)
    
    def _closeSession (self):
        """
        Close session.
        """
        self._session_cb and self._session_cb.close(self)
        try:
            self.c.killSession()
        except Glacier2.SessionNotExistException: #pragma: no cover
            pass
        except:
            logger.warn(traceback.format_exc())
                        
    def _resetOmeroClient (self):
        """
        Creates new omero.client object using self.host or self.ice_config (if host is None)
        Also tries to setAgent for the client
        """
        if self.host is not None:
            self.c = omero.client(host=str(self.host), port=int(self.port))#, pmap=['--Ice.Config='+','.join(self.ice_config)])
        else:
            self.c = omero.client(pmap=['--Ice.Config='+','.join(self.ice_config)])

        if hasattr(self.c, "setAgent"):
            if self.useragent is not None:
                self.c.setAgent(self.useragent)
            else:
                self.c.setAgent("OMERO.py.gateway")

    def connect (self, sUuid=None):
        """
        Creates or retrieves connection for the given sessionUuid.
        Returns True if connected.
        
        @param sUuid:   omero_model_SessionI
        @return:        Boolean
        """
        
        logger.debug("Connect attempt, sUuid=%s, group=%s, self.sUuid=%s" % (str(sUuid), str(self.group), self._sessionUuid))
        if not self.c: #pragma: no cover
            self._connected = False
            logger.debug("Ooops. no self._c")
            return False
        try:
            if self._sessionUuid is None and sUuid:
                self._sessionUuid = sUuid
            if self._sessionUuid is not None:
                try:
                    logger.debug('connected? %s' % str(self._connected))
                    if self._connected:
                        self._connected = False
                        logger.debug("was connected, creating new omero.client")
                        self._resetOmeroClient()
                    s = self.c.joinSession(self._sessionUuid)   # timeout to allow this is $ omero config set omero.sessions.timeout 3600000
                    s.detachOnDestroy()
                    logger.debug('Joined Session OK with Uuid: %s and timeToIdle: %s, timeToLive: %s' % (self._sessionUuid, self.getSession().timeToIdle.val, self.getSession().timeToLive.val))
                    self._was_join = True
                except Ice.SyscallException: #pragma: no cover
                    raise
                except Exception, x: #pragma: no cover
                    logger.debug("Error: " + str(x))
                    self._sessionUuid = None
                    if sUuid:
                        return False
            if self._sessionUuid is None:
                if sUuid: #pragma: no cover
                    logger.debug("Uncaptured sUuid failure!") 
                if self._connected:
                    self._connected = False
                    try:
                        logger.debug("Closing previous connection...creating new client")
                        #args = self.c._ic_args
                        #logger.debug(str(args))
                        self._closeSession()
                        self._resetOmeroClient()
                        #self.c = omero.client(*args)
                    except Glacier2.SessionNotExistException: #pragma: no cover
                        pass
                setprop = self.c.ic.getProperties().setProperty
                map(lambda x: setprop(x[0],str(x[1])), self._ic_props.items())
                if self._anonymous:
                    self.c.ic.getImplicitContext().put(omero.constants.EVENT, 'Internal')
                if self.group is not None:
                    self.c.ic.getImplicitContext().put(omero.constants.GROUP, self.group)
                try:
                    logger.debug("Creating Session...")
                    self._createSession()
                    logger.debug("Session created with timeout: %s & timeToLive: %s" % (self.getSession().timeToIdle.val, self.getSession().timeToLive.val))
                except omero.SecurityViolation:
                    if self.group is not None:
                        # User don't have access to group
                        logger.debug("## User not in '%s' group" % self.group)
                        self.group = None
                        self._closeSession()
                        self._sessionUuid = None
                        self._connected=True
                        return self.connect()
                    else: #pragma: no cover
                        logger.debug("BlitzGateway.connect().createSession(): " + traceback.format_exc())
                        logger.info('first create session threw SecurityViolation, retry (but only once)')
                        #time.sleep(10)
                        try:
                            self._createSession()
                        except omero.SecurityViolation:
                            if self.group is not None:
                                # User don't have access to group
                                logger.debug("## User not in '%s' group" % self.group)
                                self.group = None
                                self._connected=True
                                return self.connect()
                            else:
                                raise
                except Ice.SyscallException: #pragma: no cover
                    raise
                except:
                    logger.info("BlitzGateway.connect().createSession(): " + traceback.format_exc())
                    #time.sleep(10)
                    self._createSession()

            self._last_error = None
            self._createProxies()
            self._connected = True
            logger.info('created connection (uuid=%s)' % str(self._sessionUuid))
        except Ice.SyscallException: #pragma: no cover
            logger.debug('This one is a SyscallException')
            raise
        except Ice.LocalException, x: #pragma: no cover
            logger.debug("connect(): " + traceback.format_exc())
            self._last_error = x
            return False
        except Exception, x: #pragma: no cover
            logger.debug("connect(): " + traceback.format_exc())
            self._last_error = x
            return False
        logger.debug(".. connected!")
        return True

    def getLastError (self): #pragma: no cover
        """
        Returns error if thrown by _BlitzGateway.connect connect.
        
        @return: String
        """
        
        return self._last_error

    def isConnected (self):
        """
        Returns last status of connection.
        
        @return:    Boolean
        """
        
        return self._connected

    ######################
    ## Connection Stuff ##

    def getEventContext (self):
        """
        Returns omero_System_ice.EventContext.
        It containes:: 
            shareId, sessionId, sessionUuid, userId, userName, 
            groupId, groupName, isAdmin, isReadOnly, 
            eventId, eventType, eventType,
            memberOfGroups, leaderOfGroups
        Also saves context to self._ctx
        
        @return:    Event Context from admin service. 
        @rtype:     L{omero.sys.EventContext}
        """
        if self._ctx is None:
            self._ctx = self._proxies['admin'].getEventContext()
        return self._ctx

    def getUser (self):
        """
        Returns current Experimenter.
         
        @return:    Current Experimenter
        @rtype:     L{ExperimenterWrapper}
        """
        
        return self._user
    
    def getGroupFromContext(self):
        """
        Returns current omero_model_ExperimenterGroupI.
         
        @return:    omero.model.ExperimenterGroupI
        """
        
        admin_service = self.getAdminService()
        group = admin_service.getGroup(self.getEventContext().groupId)
        return ExperimenterGroupWrapper(self, group)
    
    def isAdmin (self):
        """
        Checks if a user has administration privileges.
        
        @return:    Boolean
        """
        
        return self.getEventContext().isAdmin
    
    def canBeAdmin (self):
        """
        Checks if a user is in system group, i.e. can have administration privileges.
        
        @return:    Boolean
        """
        return 0 in self.getEventContext().memberOfGroups

    def isOwner (self, gid=None):
        """
        Checks if a user has owner privileges of a particular group
        or any group if gid is not specified. 
        
        @param gid:     ID of group to check for ownership
        @type gid:      Long
        @return:    True if gid specified and owner belongs to that group
                    Otherwise True if owner belongs to any group
        """
        if gid is not None:
            if not isinstance(gid, LongType) or not isinstance(gid, IntType):
                gid = long(gid)
            for gem in self._user.copyGroupExperimenterMap():
                if gem.parent.id.val == gid and gem.owner.val == True:
                    return True
        else:
            for gem in self._user.copyGroupExperimenterMap():
                if gem.owner.val == True:
                    return True
        return False
    
    def canWrite (self, obj):
        """
        Checks if a user has write privileges to the given object.
        
        @param obj: Given object
        @return:    Boolean
        """
        
        return self.isAdmin() or (self._userid == obj.details.owner.id.val and obj.details.permissions.isUserWrite())

    def getSession (self):
        """
        Returns the existing session, or creates a new one if needed
        
        @return:    The session from session service 
        @rtype:     L{omero.model.session}
        """
        if self._session is None:
            ss = self.c.sf.getSessionService()
            self._session = ss.getSession(self._sessionUuid)
        return self._session

#    def setDefaultPermissionsForSession (self, permissions):
#        self.getSession()
#        self._session.setDefaultPermissions(rstring(permissions))
#        self._session.setTimeToIdle(None)
#        self.getSessionService().updateSession(self._session)

    def setGroupNameForSession (self, group):
        """
        Looks up the group by name, then delegates to L{setGroupForSession}, returning the result
        
        @param group:       Group name
        @type group:        String
        @return:            True if group set successfully
        @rtype:             Boolean
        """
        a = self.getAdminService()
        g = a.lookupGroup(group)
        return self.setGroupForSession(g.getId().val)

    def setGroupForSession (self, groupid):
        """
        Sets the security context of this connection to the specified group
        
        @param groupid:     The ID of the group to switch to
        @type groupid:      Long
        @rtype:             Boolean
        @return:            True if the group was switched successfully
        """
        if self.getEventContext().groupId == groupid:
            return True
        if groupid not in self._ctx.memberOfGroups:
            return False
        self._lastGroupId = self._ctx.groupId
        if hasattr(self.c.sf, 'setSecurityContext'):
            # Beta4.2
            self.c.sf.setSecurityContext(omero.model.ExperimenterGroupI(groupid, False))
        else:
            self.getSession()
            self._session.getDetails().setGroup(omero.model.ExperimenterGroupI(groupid, False))
            self._session.setTimeToIdle(None)
            self.getSessionService().updateSession(self._session)
        return True


#    def setGroupForSession (self, group):
#        self.getSession()
#        if self._session.getDetails().getGroup().getId().val == group.getId():
#            # Already correct
#            return
#        a = self.getAdminService()
#        if not group.name in [x.name.val for x in a.containedGroups(self._userid)]:
#            # User not in this group
#            return
#        self._lastGroup = self._session.getDetails().getGroup()
#        self._session.getDetails().setGroup(group._obj)
#        self._session.setTimeToIdle(None)
#        self.getSessionService().updateSession(self._session)
#
    def revertGroupForSession (self):
        """ Switches the group to the previous group """
        if self._lastGroupId is not None:
            self.setGroupForSession(self._lastGroupId)
            self._lastGroupId = None

    ##############
    ## Services ##

    def getAdminService (self):
        """
        Gets reference to the admin service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['admin']

    def getQueryService (self):
        """
        Gets reference to the query service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['query']

    def getContainerService (self):
        """
        Gets reference to the container service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['container']

    def getPixelsService (self):
        """
        Gets reference to the pixels service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['pixel']
    
    def getMetadataService (self):
        """
        Gets reference to the metadata service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['metadata']
    
    def getRoiService (self):
        """
        Gets ROI service.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['roi']
        
    def getScriptService (self):
        """
        Gets script service.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['script']
        
    def createRawFileStore (self):
        """
        Creates a new raw file store.
        This service is special in that it does not get cached inside BlitzGateway so every call to this function
        returns a new object, avoiding unexpected inherited states.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['rawfile']

    def getRepositoryInfoService (self):
        """
        Gets reference to the repository info service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['repository']

    def getShareService(self):
        """
        Gets reference to the share service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['share']

    def getTimelineService (self):
        """
        Gets reference to the timeline service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['timeline']
    
    def getTypesService(self):
        """
        Gets reference to the types service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['types']

    def getConfigService (self):
        """
        Gets reference to the config service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['config']

    def createRenderingEngine (self):
        """
        Creates a new rendering engine.
        This service is special in that it does not get cached inside BlitzGateway so every call to this function
        returns a new object, avoiding unexpected inherited states.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        rv = self._proxies['rendering']
        if rv._tainted:
            rv = self._proxies['rendering'] = rv.clone()
        rv.taint()
        return rv

    def getRenderingSettingsService (self):
        """
        Gets reference to the rendering settings service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['rendsettings']
   
    def createRawPixelsStore (self):
        """
        Creates a new raw pixels store.
        This service is special in that it does not get cached inside BlitzGateway so every call to this function
        returns a new object, avoiding unexpected inherited states.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['rawpixels']

    def createThumbnailStore (self):
        """
        Gets a reference to the thumbnail store on this connection object or creates a new one
        if none exists.
        
        @rtype: omero.gateway.ProxyObjectWrapper
        @return: The proxy wrapper of the thumbnail store
        """
        
        return self._proxies['thumbs']
    
    def createSearchService (self):
        """
        Gets a reference to the searching service on this connection object or creates a new one
        if none exists.
        
        @return: omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['search']

    def getUpdateService (self):
        """
        Gets reference to the update service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['update']

    def getDeleteService (self):
        """
        Gets reference to the delete service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['delete']

    def getSessionService (self):
        """
        Gets reference to the session service from ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        return self._proxies['session']

    def createExporter (self):
        """
        New instance of non cached Exporter, wrapped in ProxyObjectWrapper.
        
        @return:    omero.gateway.ProxyObjectWrapper
        """
        
        return self._proxies['export']

    #############################
    # Top level object fetchers #

    def listProjects (self, eid=None, only_owned=False):
        """
        List every Project controlled by the security system.

        @param eid:         Filters Projects by owner ID
        @param only_owned:  Short-cut for filtering Projects by current user
        @rtype:             L{ProjectWrapper} list
        """

        params = omero.sys.Parameters()
        params.theFilter = omero.sys.Filter()
        if only_owned:
            params.theFilter.ownerId = rlong(self._userid)
        elif eid is not None:
            params.theFilter.ownerId = rlong(eid)

        return self.getObjects("Project", params=params)

    #################################################
    ## IAdmin
    
    # GROUPS
    
    def findGroup(self, name):
        """ 
        Look up a Group and all contained users by group name.
        
        @param name:    Group name
        @type name:     String
        @return:        The named group
        @rtype:         L{ExperimenterGroupWrapper}
        """
        
        admin_service = self.getAdminService()
        group = admin_service.lookupGroup(str(name))
        return ExperimenterGroupWrapper(self, group)
    
    def getDefaultGroup(self, eid):
        """
        Retrieve the default group for the given user id.
        
        @param eid:     Experimenter ID
        @type eid:      Long
        @return:        The default group for user
        @rtype:         L{ExperimenterGroupWrapper}
        """
        
        admin_serv = self.getAdminService()
        dgr = admin_serv.getDefaultGroup(long(eid))
        return ExperimenterGroupWrapper(self, dgr)
    
    def getOtherGroups(self, eid):
        """ 
        Fetch all groups of which the given user is a member. 
        The returned groups will have all fields filled in and all collections unloaded.
        
        @param eid:         Experimenter ID
        @type eid:          Long
        @return:            Generator of groups for user
        @rtype:             L{ExperimenterGroupWrapper} generator
        """
        
        admin_serv = self.getAdminService()
        for gr in admin_serv.containedGroups(long(eid)):
            yield ExperimenterGroupWrapper(self, gr)
        
    def getGroupsLeaderOf(self):
        """ 
        Look up Groups where current user is a leader of.
        
        @return:        Groups that current user leads
        @rtype:         L{ExperimenterGroupWrapper} generator
        """
         
        q = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["ids"] = rlist([rlong(a) for a in self.getEventContext().leaderOfGroups])
        sql = "select e from ExperimenterGroup as e where e.id in (:ids)"
        for e in q.findAllByQuery(sql, p):
            yield ExperimenterGroupWrapper(self, e)

    def getGroupsMemberOf(self):
        """ 
        Look up Groups where current user is a member of (except "user" group).
        
        @return:        Current users groups
        @rtype:         L{ExperimenterGroupWrapper} generator
        """
        
        q = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["ids"] = rlist([rlong(a) for a in self.getEventContext().memberOfGroups])
        sql = "select e from ExperimenterGroup as e where e.id in (:ids)"
        for e in q.findAllByQuery(sql, p):
            if e.name.val == "user":
                pass
            else:
                yield ExperimenterGroupWrapper(self, e)
 
    # EXPERIMENTERS
        
    def listExperimenters(self):
        """ 
        Look up all experimenters and related groups.
        Groups are also loaded
        
        @return:    All experimenters
        @rtype:     L{ExperimenterWrapper} generator
        """
        
        admin_serv = self.getAdminService()
        for exp in admin_serv.lookupExperimenters():
            yield ExperimenterWrapper(self, exp)

    def findExperimenters (self, start=''):
        """
        Return a generator for all Experimenters whose omeName starts with 'start'.
        Experimenters ordered by omeName.
        
        @param start:   omeName must start with these letters
        @type start:    String
        @return:        Generator of experimenters
        @rtype:         L{ExperimenterWrapper} generator
        """
        
        if isinstance(start, UnicodeType):
            start = start.encode('utf8')
        params = omero.sys.Parameters()
        params.map = {'start': rstring('%s%%' % start.lower())}
        q = self.getQueryService()
        rv = q.findAllByQuery("from Experimenter e where lower(e.omeName) like :start", params)
        rv.sort(lambda x,y: cmp(x.omeName.val,y.omeName.val))
        for e in rv:
            yield ExperimenterWrapper(self, e)

    def getExperimenter(self, eid):
        """
        Return an Experimenter for the given ID.
        
        @param eid:     User ID.
        @type:          Long
        @return:        Experimenter or None
        @rtype:         L{ExperimenterWrapper}
        """
        
        admin_serv = self.getAdminService()
        try:
            exp = admin_serv.getExperimenter(long(eid))
            return ExperimenterWrapper(self, exp)
        except omero.ApiUsageException:
            return None

    def findExperimenter(self, name):
        """
        Return an Experimenter for the given username.
        
        @param name:    Username. 
        @type:          String
        @return:        Experimenter or None
        @rtype:         L{ExperimenterWrapper}
        """
        
        admin_serv = self.getAdminService()
        try:
            exp = admin_serv.lookupExperimenter(str(name))
            return ExperimenterWrapper(self, exp)
        except omero.ApiUsageException:
            return None

    def containedExperimenters(self, gid):
        """ 
        Fetch all users contained in this group. 
        The returned users will have all fields filled in and all collections unloaded.
        
        @param gid:     Group ID
        @type gid:      Long
        @return:        Generator of experimenters
        @rtype:         L{ExperimenterWrapper} generator
        """
        
        admin_serv = self.getAdminService()
        for exp in admin_serv.containedExperimenters(long(gid)):
            yield ExperimenterWrapper(self, exp)
    
    def listColleagues(self):
        """
        Look up users who are a member of the current user active group.
        Returns None if the group is private and isn't lead by the current user
        
        @return:    Generator of Experimenters or None
        @rtype:     L{ExperimenterWrapper} generator
        """
                
        default = self.getObject("ExperimenterGroup", self.getEventContext().groupId)
        if not default.isPrivate() or default.isLeader():
            for d in default.copyGroupExperimenterMap():
                if d.child.id.val != self.getEventContext().userId:
                    yield ExperimenterWrapper(self, d.child)

    def listStaffs(self):
        """
        Look up users who are members of groups lead by the current user.
        
        @return:    Members of groups lead by current user
        @rtype:     L{ExperimenterWrapper} generator
        """
        
        q = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["gids"] = rlist([rlong(a) for a in set(self.getEventContext().leaderOfGroups)])
        sql = "select e from Experimenter as e where " \
                "exists ( select gem from GroupExperimenterMap as gem where gem.child = e.id " \
                "and gem.parent.id in (:gids)) order by e.omeName"
        for e in q.findAllByQuery(sql, p):
            if e.id.val != self.getEventContext().userId:
                yield ExperimenterWrapper(self, e)

    def listOwnedGroups(self):
        """
        Looks up owned groups for the logged user.
        
        @return:    Groups owned by current user
        @rtype:     L{ExperimenterGroupWrapper} generator
        """
            
        exp = self.getUser()
        for gem in exp.copyGroupExperimenterMap():
            if gem.owner.val:
                yield ExperimenterGroupWrapper(self, gem.parent)
    
    def getFreeSpace(self):
        """ 
        Returns the free or available space on this file system
        including nested subdirectories.
        
        @return:    Free space in bytes
        @rtype:     Int
        """
        
        rep_serv = self.getRepositoryInfoService()
        return rep_serv.getFreeSpaceInKilobytes() * 1024
    
    ############################
    # Timeline service getters #

    def timelineListImages (self, tfrom=None, tto=None, limit=10, only_owned=True):
        """
        List images based on their creation times.
        If both tfrom and tto are None, grab the most recent batch.
        
        @param tfrom:       milliseconds since the epoch for start date
        @param tto:         milliseconds since the epoch for end date
        @param limit:       maximum number of results
        @param only_owned:  Only owned by the logged user. Boolean.
        @return:            Generator yielding _ImageWrapper
        @rtype:             L{ImageWrapper} generator
        """
        
        tm = self.getTimelineService()
        p = omero.sys.Parameters()
        f = omero.sys.Filter()
        if only_owned:
            f.ownerId = rlong(self.getEventContext().userId)
            f.groupId = rlong(self.getEventContext().groupId)
        else:
            f.ownerId = rlong(-1)
            f.groupId = None
        f.limit = rint(limit)
        p.theFilter = f
        if tfrom is None and tto is None:
            for e in tm.getMostRecentObjects(['Image'], p, False)["Image"]:
                yield ImageWrapper(self, e)
        else:
            if tfrom is None:
                tfrom = 0
            if tto is None:
                tto = time.time() * 1000
            for e in tm.getByPeriod(['Image'], rtime(long(tfrom)), rtime(long(tto)), p, False)['Image']:
                yield ImageWrapper(self, e)


    ###########################
    # Specific Object Getters #


    def getObject (self, obj_type, oid=None, params=None, attributes=None):
        """
        Convenience method for L{getObjects}. Returns a single wrapped object or None. 
        """
        oids = (oid!=None) and [oid] or None
        result = list(self.getObjects(obj_type, oids, params=params, attributes=attributes))
        if len(result) == 0:
            return None
        elif len(result) > 1:
            raise RuntimeError("More than one result returned for getObject('%s', %s, %s)" % (obj_type, oid, attributes))
        return result[0]


    def getObjects (self, obj_type, ids=None, params=None, attributes=None):
        """
        Retrieve Objects by type E.g. "Image". Not Ordered. 
        Returns generator of appropriate L{BlitzObjectWrapper} type. E.g. L{ImageWrapper}.
        If ids is None, all available objects will be returned. i.e. listObjects()
        
        @param obj_type:    Object type. E.g. "Project" see above
        @type obj_type:     String
        @param ids:         object IDs
        @type ids:          List of Long
        @param params:      omero.sys.Parameters, can be used for pagination, filtering etc.
        @param attributes:  Map of key-value pairs to filter results by. Key must be attribute of obj_type. E.g. 'name', 'ns'
        @return:            Generator yielding wrapped objects.
        """

        if type(obj_type) is type(''):
            wrapper = KNOWN_WRAPPERS.get(obj_type.lower(), None)
            if wrapper is None:
                raise KeyError("obj_type of %s not supported by getOjbects(). E.g. use 'Image' etc" % obj_type)
        else:
            raise AttributeError("getObjects uses a string to define obj_type, E.g. 'Image'")

        q = self.getQueryService()
        if params is None:
            params = omero.sys.Parameters()
        if params.map is None:
            params.map = {}

        # get the base query from the instantiated object itself. E.g "select obj Project as obj"
        query = wrapper()._getQueryString()

        clauses = []
        # getting object by ids
        if ids != None:
            clauses.append("obj.id in (:ids)")
            params.map["ids"] = rlist([rlong(a) for a in ids])

        # support filtering by owner (not for some object types)
        if params.theFilter and params.theFilter.ownerId and obj_type.lower() not in ["experimentergroup", "experimenter"]:
            clauses.append("owner.id = (:eid)")
            params.map["eid"] = params.theFilter.ownerId

        # finding by attributes
        if attributes != None:
            for k,v in attributes.items():
                clauses.append('obj.%s=:%s' % (k, k) )
                params.map[k] = omero_type(v)

        if clauses:
            query += " where " + (" and ".join(clauses))

        result = q.findAllByQuery(query, params)
        for r in result:
            yield wrapper(self, r)


    def listFileAnnotations (self, eid=None, toInclude=[], toExclude=[]):
        """
        Lists FileAnnotations created by users, filtering by namespaces if specified.
        If NO namespaces are specified, then 'known' namespaces are excluded by default,
        such as original files and companion files etc.
        File objects are loaded so E.g. file name is available without lazy loading.

        @param eid:         Filter results by this owner Id
        @param toInclude:   Only return annotations with these namespaces. List of strings.
        @param toExclude:   Don't return annotations with these namespaces. List of strings.
        @return:            Generator of L{FileAnnotationWrapper}s - with files loaded.
        """

        params = omero.sys.Parameters()
        params.theFilter = omero.sys.Filter()
        if eid is not None:
            params.theFilter.ownerId = rlong(eid)

        if len(toInclude) == 0 and len(toExclude) == 0:
            toExclude.append(omero.constants.namespaces.NSCOMPANIONFILE)
            toExclude.append(omero.constants.annotation.file.ORIGINALMETADATA)
            toExclude.append(omero.constants.namespaces.NSEXPERIMENTERPHOTO)
            toExclude.append(omero.constants.analysis.flim.NSFLIM)

        anns = self.getMetadataService().loadSpecifiedAnnotations("FileAnnotation", toInclude, toExclude, params)

        for a in anns:
            yield(FileAnnotationWrapper(self, a))


    def getAnnotationLinks (self, parent_type, parent_ids=None, ann_ids=None, ns=None, params=None):
        """
        Retrieve Annotation Links by parent_type E.g. "Image". Not Ordered. 
        Returns generator of L{AnnotationLinkWrapper}
        If parent_ids is None, all available objects will be returned. i.e. listObjects()

        @param obj_type:    Object type. E.g. "Project" see above
        @type obj_type:     String
        @param ids:         object IDs
        @type ids:          List of Long
        @return:            Generator yielding wrapped objects.
        """

        if parent_type not in ["Project", "Dataset", "Image", "Screen", "Plate"]:
            raise AttributeError("Can only get Annotations on 'Project', 'Dataset', 'Image', 'Screen', 'Plate'")
        wrapper = KNOWN_WRAPPERS.get(parent_type.lower(), None)

        query = "select annLink from %sAnnotationLink as annLink join fetch annLink.details.owner as owner " \
                "join fetch annLink.details.creationEvent " \
                "join fetch annLink.child as ann join fetch ann.details.owner join fetch ann.details.creationEvent "\
                "join fetch annLink.parent as parent" % wrapper().OMERO_CLASS

        q = self.getQueryService()
        if params is None:
            params = omero.sys.Parameters()
        if params.map is None:
            params.map = {}

        clauses = []
        if parent_ids:
            clauses.append("parent.id in (:pids)")
            params.map["pids"] = rlist([rlong(a) for a in parent_ids])

        if ann_ids:
            clauses.append("ann.id in (:ann_ids)")
            params.map["ann_ids"] = rlist([rlong(a) for a in ann_ids])

        if ns:
            clauses.append("ann.ns in (:ns)")
            params.map["ns"] = rstring(ns)

        if params.theFilter and params.theFilter.ownerId:
            clauses.append("owner.id = (:eid)")
            params.map["eid"] = params.theFilter.ownerId

        if len(clauses) > 0:
            query += " where %s" % (" and ".join(clauses))

        result = q.findAllByQuery(query, params)
        for r in result:
            yield AnnotationLinkWrapper(self, r)


    def createImageFromNumpySeq (self, zctPlanes, imageName, sizeZ=1, sizeC=1, sizeT=1, description=None, dataset=None):
        """
        Creates a new multi-dimensional image from the sequence of 2D numpy arrays in zctPlanes.
        zctPlanes should be a generator of numpy 2D arrays of shape (sizeY, sizeX) ordered
        to iterate through T first, then C then Z.
        Example usage:
        original = conn.getObject("Image", 1)
        sizeZ = original.getSizeZ()
        sizeC = original.getSizeC()
        sizeT = original.getSizeT()
        zctList = []
        for z in range(sizeZ):
            for c in range(sizeC):
                for t in range(sizeT):
                    zctList.append( (z,c,t) )
        def planeGen():
            planes = original.getPrimaryPixels().getPlanes(zctList)
            for p in planes:
                # perform some manipulation on each plane
                yield p
        createImageFromNumpySeq (planeGen(), imageName, sizeZ=sizeZ, sizeC=sizeC, sizeT=sizeT

        @param session          An OMERO service factory or equivalent with getQueryService() etc.
        @param zctPlanes        A generator of numpy 2D arrays, corresponding to Z-planes of new image.
        @param imageName        Name of new image
        @param description      Description for the new image
        @param dataset          If specified, put the image in this dataset. omero.model.Dataset object

        @return The new OMERO image: omero.model.ImageI
        """
        queryService = self.getQueryService()
        pixelsService = self.getPixelsService()
        rawPixelsStore = self.c.sf.createRawPixelsStore()    # Make sure we don't get an existing rpStore
        #renderingEngine = self.createRenderingEngine()
        containerService = self.getContainerService()
        updateService = self.getUpdateService()

        def createImage(firstPlane):
            """ Create our new Image once we have the first plane in hand """
            # need to map numpy pixel types to omero - don't handle: bool_, character, int_, int64, object_
            pTypes = {'int8':'int8', 'int16':'int16', 'uint16':'uint16', 'int32':'int32', 'float_':'float', 'float8':'float', 
                        'float16':'float', 'float32':'float', 'float64':'double', 'complex_':'complex', 'complex64':'complex'}
            dType = firstPlane.dtype.name
            if dType not in pTypes: # try to look up any not named above
                pType = dType
            else:
                pType = pTypes[dType]
            pixelsType = queryService.findByQuery("from PixelsType as p where p.value='%s'" % pType, None) # omero::model::PixelsType
            if pixelsType is None:
                raise Exception("Cannot create an image in omero from numpy array with dtype: %s" % dType)
            sizeY, sizeX = firstPlane.shape
            channelList = range(1, sizeC+1)
            iId = pixelsService.createImage(sizeX, sizeY, sizeZ, sizeT, channelList, pixelsType, imageName, description)
            imageId = iId.getValue()
            return containerService.getImages("Image", [imageId], None)[0]

        def uploadPlane(plane, z, c, t):
            byteSwappedPlane = plane.byteswap();
            convertedPlane = byteSwappedPlane.tostring();
            rawPixelsStore.setPlane(convertedPlane, z, c, t)

        image = None
        channelsMinMax = []
        exc = None
        try:
            for theZ in range(sizeZ):
                for theC in range(sizeC):
                    for theT in range(sizeT):
                        plane = zctPlanes.next()
                        if image == None:   # use the first plane to create image.
                            image = createImage(plane)
                            pixelsId = image.getPrimaryPixels().getId().getValue()
                            rawPixelsStore.setPixelsId(pixelsId, True)
                        uploadPlane(plane, theZ, theC, theT)
                        # init or update min and max for this channel
                        minValue = plane.min()
                        maxValue = plane.max()
                        if len(channelsMinMax) < (theC +1):     # first plane of each channel
                            channelsMinMax.append( [minValue, maxValue] )
                        else:
                            channelsMinMax[theC][0] = min(channelsMinMax[theC][0], minValue)
                            channelsMinMax[theC][1] = max(channelsMinMax[theC][1], maxValue)
        except Exception, e:
            logger.error("Failed to setPlane() on rawPixelsStore while creating Image", exc_info=True)
            exc = e
        try:
            rawPixelsStore.close()
        except Exception, e:
            logger.error("Failed to close rawPixelsStore", exc_info=True)
            if exc is None:
                 exc = e
        if exc is not None:
           raise exc

        try:    # simply completing the generator - to avoid a GeneratorExit error.
            zctPlanes.next()
        except StopIteration:
            pass

        for theC, mm in enumerate(channelsMinMax):
            pixelsService.setChannelGlobalMinMax(pixelsId, theC, float(mm[0]), float(mm[1]))
            #resetRenderingSettings(renderingEngine, pixelsId, theC, mm[0], mm[1])

        # put the image in dataset, if specified.
        if dataset:
            link = omero.model.DatasetImageLinkI()
            link.parent = omero.model.DatasetI(dataset.getId(), False)
            link.child = omero.model.ImageI(image.id.val, False)
            updateService.saveObject(link)

        return ImageWrapper(self, image)


    def createFileAnnfromLocalFile (self, localPath, origFilePathAndName=None, mimetype=None, ns=None, desc=None):
        """
        Class method to create a L{FileAnnotationWrapper} from a local file.
        File is uploaded to create an omero.model.OriginalFileI referenced from this File Annotation.
        Returns a new L{FileAnnotationWrapper}

        @param conn:                    Blitz connection
        @param localPath:               Location to find the local file to upload
        @param origFilePathAndName:     Provides the 'path' and 'name' of the OriginalFile. If None, use localPath
        @param mimetype:                The mimetype of the file. String. E.g. 'text/plain'
        @return:                        New L{FileAnnotationWrapper}
        """
        updateService = self.getUpdateService()
        rawFileStore = self.createRawFileStore()

        # create original file, set name, path, mimetype
        if origFilePathAndName is None:
            origFilePathAndName = localPath
        originalFile = omero.model.OriginalFileI()
        path, name = os.path.split(origFilePathAndName)
        originalFile.setName(rstring(name))
        originalFile.setPath(rstring(path))
        if mimetype:
            originalFile.mimetype = rstring(mimetype)
        fileSize = os.path.getsize(localPath)
        originalFile.setSize(rlong(fileSize))
        # set sha1
        try:
            import hashlib
            hash_sha1 = hashlib.sha1
        except:
            import sha
            hash_sha1 = sha.new
        fileHandle = open(localPath)
        h = hash_sha1()
        h.update(fileHandle.read())
        shaHast = h.hexdigest()
        fileHandle.close()
        originalFile.setSha1(rstring(shaHast))
        originalFile = updateService.saveAndReturnObject(originalFile)

        # upload file
        rawFileStore.setFileId(originalFile.getId().getValue())
        fileHandle = open(localPath, 'rb')
        buf = 10000
        for pos in range(0,long(fileSize),buf):
            block = None
            if fileSize-pos < buf:
                blockSize = fileSize-pos
            else:
                blockSize = buf
            fileHandle.seek(pos)
            block = fileHandle.read(blockSize)
            rawFileStore.write(block, pos, blockSize)
        fileHandle.close()

        # create FileAnnotation, set ns & description and return wrapped obj
        fa = omero.model.FileAnnotationI()
        fa.setFile(originalFile)
        if desc:
            fa.setDescription(rstring(desc))
        if ns:
            fa.setNs(rstring(ns))
        fa = updateService.saveAndReturnObject(fa)
        return FileAnnotationWrapper(self, fa)

    def getObjectsByAnnotations(self, obj_type, annids):
        """
        Retrieve objects linked to the given annotation IDs
        controlled by the security system.
        
        @param annids:      Annotation IDs
        @type annids:       L{Long}
        @return:            Generator yielding Objects
        @rtype:             L{BlitzObjectWrapper} generator
        """
        
        wrappers = {"Project":ProjectWrapper,
            "Dataset":DatasetWrapper,
            "Image":ImageWrapper,
            "Screen":ScreenWrapper,
            "Plate":PlateWrapper,
            "Well":WellWrapper}
            
        if not obj_type in wrappers:
            raise AttributeError('It only retrieves: Project, Dataset, Image, Screen, Plate or Well')
        
        sql = "select ob from %s ob " \
              "left outer join fetch ob.annotationLinks obal " \
              "left outer join fetch obal.child ann " \
              "where ann.id in (:oids)" % obj_type
            
        q = self.getQueryService()
        p = omero.sys.Parameters()
        p.map = {}
        p.map["oids"] = rlist([rlong(o) for o in set(annids)])
        for e in q.findAllByQuery(sql,p):
            kwargs = {'link': BlitzObjectWrapper(self, e.copyAnnotationLinks()[0])}
            yield wrappers[obj_type](self, e)


    ################
    # Enumerations #
    
    def getEnumerationEntries(self, klass):
        """
        Get all enumerations by class
        
        @param klass:   Class
        @type klass:    Class or string
        @return:        Generator of Enumerations
        @rtype:         L{EnumerationWrapper} generator
        """
        
        types = self.getTypesService()
        for e in types.allEnumerations(str(klass)):
            yield EnumerationWrapper(self, e)
    
    def getEnumeration(self, klass, string):
        """
        Get enumeration by class and value
        
        @param klass:   Class
        @type klass:    Class or string
        @param string:  Enum value
        @type string:   String
        @return:        Enumeration or None
        @rtype:         L{EnumerationWrapper}
        """
        
        types = self.getTypesService()
        obj = types.getEnumeration(str(klass), str(string))
        if obj is not None:
            return EnumerationWrapper(self, obj)
        else:
            return None
    
    def getEnumerationById(self, klass, eid):
        """
        Get enumeration by class and ID
        
        @param klass:   Class
        @type klass:    Class or string
        @param eid:     Enum ID
        @type eid:      Long
        @return:        Enumeration or None
        @rtype:         L{EnumerationWrapper}
        """
        
        query_serv = self.getQueryService()
        obj =  query_serv.find(klass, long(eid))
        if obj is not None:
            return EnumerationWrapper(self, obj)
        else:
            return None
            
    def getOriginalEnumerations(self):
        """
        Gets original enumerations. Returns a dictionary of enumeration class: list of Enumerations
        
        @return:    Original enums
        @rtype:     Dict of <string: L{EnumerationWrapper} list >
        """
        
        types = self.getTypesService()
        rv = dict()
        for e in types.getOriginalEnumerations():
            if rv.get(e.__class__.__name__) is None:
                rv[e.__class__.__name__] = list()
            rv[e.__class__.__name__].append(EnumerationWrapper(self, e))
        return rv
        
    def getEnumerations(self):
        """
        Gets list of enumeration types
        
        @return:    List of enum types
        @rtype:     List of Strings
        """
        
        types = self.getTypesService()
        return types.getEnumerationTypes() 
    
    def getEnumerationsWithEntries(self):
        """
        Get enumeration types, with lists of Enum entries
        
        @return:    Dictionary of type: entries
        @rtype:     Dict of <string: L{EnumerationWrapper} list >
        """
        
        types = self.getTypesService()
        rv = dict()
        for key, value in types.getEnumerationsWithEntries().items():
            r = list()
            for e in value:
                r.append(EnumerationWrapper(self, e))
            rv[key+"I"] = r
        return rv
    
    def deleteEnumeration(self, obj):
        """
        Deletes an enumeration object
        
        @param obj:     Enumeration object
        @type obj:      omero.model.IObject
        """
        
        types = self.getTypesService()
        types.deleteEnumeration(obj)
        
    def createEnumeration(self, obj):
        """
        Create an enumeration with given object 
        
        @param obj:     Object
        @type obj:      omero.model.IObject
        """
        
        types = self.getTypesService()
        types.createEnumeration(obj)
    
    def resetEnumerations(self, klass):
        """
        Resets the enumerations by type
        
        @param klass:   Type of enum to reset
        @type klass:    String
        """
        
        types = self.getTypesService()
        types.resetEnumerations(klass)
    
    def updateEnumerations(self, new_entries):
        """
        Updates enumerations with new entries
        
        @param new_entries:   List of objects
        @type new_entries:    List of omero.model.IObject
        """
        
        types = self.getTypesService()
        types.updateEnumerations(new_entries)
    
    ###################
    # Delete          #
    
    def deleteObjectDirect(self, obj):
        """
        Directly Delete object (removes row from database).
        This may fail with various constraint violations if the object is linked to others in the database
        
        @param obj:     Object to delete
        @type obj:      IObject"""
        
        u = self.getUpdateService() 
        u.deleteObject(obj)

    def deleteObjects(self, obj_type, obj_ids, deleteAnns=False, deleteChildren=False):
        """
        Generic method for deleting using the delete queue. 
        Supports deletion of 'Project', 'Dataset', 'Image', 'Screen', 'Plate', 'Well', 'Annotation'.
        Options allow to delete 'independent' Annotations (Tag, Term, File) and to delete child objects.

        @param obj_type:        String to indicate 'Project', 'Image' etc. 
        @param obj_ids:         List of IDs for the objects to delete
        @param deleteAnns:      If true, delete linked Tag, Term and File annotations
        @param deleteChildren:  If true, delete children. E.g. Delete Project AND it's Datasets & Images.  
        @return:                Delete handle
        @rtype:                 L{omero.api.delete.DeleteHandle}
        """

        if not isinstance(obj_ids, list) and len(obj_ids) < 1:
            raise AttributeError('Must be a list of object IDs')

        op = dict()
        if not deleteAnns and obj_type not in ["Annotation", "TagAnnotation"]:
            op["/TagAnnotation"] = "KEEP"
            op["/TermAnnotation"] = "KEEP"
            op["/FileAnnotation"] = "KEEP"

        childTypes = {'Project':['/Dataset', '/Image'],
                'Dataset':['/Image'],
                'Image':[],
                'Screen':['/Plate'],
                'Plate':[],
                'Well':[],
                'Annotation':[] }
    
        obj_type = obj_type.title()
        if obj_type not in childTypes:
            m = """%s is not an object type. Must be: Project, Dataset, Image, Screen, Plate, Well, Annotation""" % obj_type
            raise AttributeError(m)
        if not deleteChildren:
            for c in childTypes[obj_type]:
                op[c] = "KEEP"

        #return self.simpleDelete(obj_type, obj_ids, op)
        dcs = list()
        logger.debug('Deleting %s [%s]. Children: %s' % (obj_type, str(obj_ids), deleteChildren))
        for oid in obj_ids:
            dcs.append(omero.api.delete.DeleteCommand("/%s" % obj_type, long(oid), op))
        handle = self.getDeleteService().queueDelete(dcs)
        return handle


    ###################
    # Searching stuff #

    def searchObjects(self, obj_types, text, created=None):
        """
        Search objects of type "Project", "Dataset", "Image", "Screen", "Plate"
        Returns a list of results
        
        @param obj_types:   E.g. ["Dataset", "Image"]
        @param text:        The text to search for
        @param created:     L{omero.rtime} list or tuple (start, stop)
        @return:            List of Object wrappers. E.g. L{ImageWrapper}
        """
        if not text:
            return []
        if isinstance(text, UnicodeType):
            text = text.encode('utf8')
        if obj_types is None:
            types = (ProjectWrapper, DatasetWrapper, ImageWrapper)
        else:
            def getWrapper(obj_type):
                if obj_type.lower() not in ["project", "dataset", "image", "screen", "plate"]:
                    raise AttributeError("%s not recognised. Can only search for 'Project', 'Dataset', 'Image', 'Screen', 'Plate'" % obj_type)
                return KNOWN_WRAPPERS.get(obj_type.lower(), None)
            types = [getWrapper(o) for o in obj_types]
        search = self.createSearchService()
        if created:
            search.onlyCreatedBetween(created[0], created[1]);
        if text[0] in ('?','*'):
            search.setAllowLeadingWildcard(True)
        rv = []
        for t in types:
            def actualSearch ():
                search.onlyType(t().OMERO_CLASS)
                search.byFullText(text)
            timeit(actualSearch)()
            if search.hasNext():
                def searchProcessing ():
                    rv.extend(map(lambda x: t(self, x), search.results()))
                timeit(searchProcessing)()
        search.close()
        return rv


def safeCallWrap (self, attr, f): #pragma: no cover
    """
    Wraps a function call. Does not call the function. Throws an exception.
    
    @param self:    Wrapped object
    @param attr:    Function name
    @type attr:     String
    @param f:       Function to wrap
    @type f:        Function
    @return:        Wrapped function
    @rtype:         Function
    """
    
    def inner (*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except omero.ResourceError:
            logger.debug( "omero.ResourceError on safeCallWrap %s(%s,%s)" % (attr, str(args), str(kwargs)))
            logger.debug(traceback.format_exc())
            raise
        except omero.SecurityViolation:
            logger.debug( "omero.SecurityViolation on safeCallWrap %s(%s,%s)" % (attr, str(args), str(kwargs)))
            logger.debug(traceback.format_exc())
            raise
        except omero.ApiUsageException:
            logger.debug( "omero.ApiUsageException on safeCallWrap %s(%s,%s)" % (attr, str(args), str(kwargs)))
            logger.debug(traceback.format_exc())
            raise
        except Ice.MemoryLimitException:
            logger.debug( "omero.MemoryLimitException on safeCallWrap %s(%s,%s)" % (attr, str(args), str(kwargs)))
            logger.debug(traceback.format_exc())
            raise
        except omero.InternalException:
            logger.debug( "omero.InternalException on safeCallWrap %s(%s,%s)" % (attr, str(args), str(kwargs)))
            logger.debug(traceback.format_exc())
            raise
        except omero.ConcurrencyException:
            logger.debug( "omero.ConcurrencyException on safeCallWrap %s(%s,%s)" % (attr, str(args), str(kwargs)))
            logger.debug(traceback.format_exc())
            raise # ticket:5835
        except Ice.Exception, x:
            # Failed
            logger.debug( "Ice.Exception (1) on safe call %s(%s,%s)" % (attr, str(args), str(kwargs)))
            logger.debug(traceback.format_exc())
            # Recreate the proxy object
            try:
                self._obj = self._create_func()
                func = getattr(self._obj, attr)
                return func(*args, **kwargs)
            except Ice.MemoryLimitException:
                raise
            except Ice.Exception, x:
                # Still Failed
                logger.debug("Ice.Exception (2) on safe call %s(%s,%s)" % (attr, str(args), str(kwargs)))
                logger.debug(traceback.format_exc())
                try:
#                    if self._conn.c.sf.getSessionService().getReferenceCount(self._conn._sessionUuid) > 0:
                    # Recreate connection
                    self._connect(forcejoin=True)
                    logger.debug('last try for %s' % attr)
                    # Last try, don't catch exception
                    func = getattr(self._obj, attr)
                    return func(*args, **kwargs)
#                    raise Ice.ConnectionLostException()
                except Ice.ObjectNotExistException:
                    raise Ice.ConnectionLostException()
                except Ice.CommunicatorDestroyedException:
                    raise Ice.ConnectionLostException()
                except:
                    raise

    def wrapped (*args, **kwargs): #pragma: no cover
        try:
            return inner(*args, **kwargs)
        except Ice.MemoryLimitException:
            logger.debug("MemoryLimitException! abort, abort...")
            raise
        except omero.SecurityViolation:
            logger.debug("SecurityViolation, bailing out")
            raise
        except omero.ApiUsageException:
            logger.debug("ApiUsageException, bailing out")
            raise
        except omero.ConcurrencyException:
            logger.debug("ConcurrencyException, bailing out")
            raise
        except Ice.UnknownException:
            logger.debug("UnknownException, bailing out")
            raise
        except Ice.ConnectionLostException:
            logger.debug("ConnectionLostException, bailing out")
            raise
        except Ice.CommunicatorDestroyedException:
            logger.debug("CommunicatorDestroyedException, bailing out")
            raise
        except Ice.Exception, x:
            logger.debug('wrapped ' + f.func_name)
            logger.debug(x.__dict__)
            if hasattr(x, 'serverExceptionClass') and x.serverExceptionClass == 'ome.conditions.InternalException':
                if x.message.find('java.lang.NullPointerException') > 0:
                    logger.debug("NullPointerException, bailing out")
                    raise
                elif x.message.find('Session is dirty') >= 0:
                    logger.debug("Session is dirty, bailing out")
                    raise
                else:
                    logger.debug(x.message)
            logger.debug("exception caught, first time we back off for 10 secs")
            logger.debug(traceback.format_exc())
            #time.sleep(10)
            return inner(*args, **kwargs)
    return wrapped


BlitzGateway = _BlitzGateway


def splitHTMLColor (color):
    """ splits an hex stream of characters into an array of bytes in format (R,G,B,A).
    - abc      -> (0xAA, 0xBB, 0xCC, 0xFF)
    - abcd     -> (0xAA, 0xBB, 0xCC, 0xDD)
    - abbccd   -> (0xAB, 0xBC, 0xCD, 0xFF)
    - abbccdde -> (0xAB, 0xBC, 0xCD, 0xDE)
    
    @param color:   Characters to split.
    @return:        rgba
    @rtype:         list of Ints
    """
    try:
        out = []
        if len(color) in (3,4):
            c = color
            color = ''
            for e in c:
                color += e + e
        if len(color) == 6:
            color += 'FF'
        if len(color) == 8:
            for i in range(0, 8, 2):
                out.append(int(color[i:i+2], 16))
            return out
    except:
        pass
    return None


class ProxyObjectWrapper (object):
    """
    Wrapper for services. E.g. Admin Service, Delete Service etc. 
    Maintains reference to connection. 
    Handles creation of service when requested. 
    """
    
    def __init__ (self, conn, func_str):
        """
        Initialisation of proxy object wrapper. 
        
        @param conn:        The L{BlitzGateway} connection
        @type conn:         L{BlitzGateway}
        @param func_str:    The name of the service creation method. E.g 'getAdminService'
        @type func_str:     String
        """
        self._obj = None
        self._func_str = func_str
        self._resyncConn(conn)
        self._tainted = False
    
    def clone (self):
        """
        Creates and returns a new L{ProxyObjectWrapper} with the same connection 
        and service creation method name as this one. 
        
        @return:    Cloned service wrapper
        @rtype:     L{ProxyObjectWrapper}
        """
        
        return ProxyObjectWrapper(self._conn, self._func_str)

    def _connect (self, forcejoin=False): #pragma: no cover
        """
        Returns True if connected. If connection OK, wrapped service is also created. 

        @param forcejoin: if True forces the connection to only succeed if we can
                          rejoin the current sessionid
        @type forcejoin:  Boolean
        
        @return:    True if connection OK
        @rtype:     Boolean
        """
        logger.debug("proxy_connect: a");
        if forcejoin:
            sUuid = self._conn._sessionUuid
        else:
            sUuid = None
        if not self._conn.connect(sUuid=sUuid):
            logger.debug('connect failed')
            logger.debug('/n'.join(traceback.format_stack()))
            return False
        logger.debug("proxy_connect: b");
        self._resyncConn(self._conn)
        logger.debug("proxy_connect: c");
        self._obj = self._create_func()
        logger.debug("proxy_connect: d");
        return True

    def taint (self):
        """ Sets the tainted flag to True """
        self._tainted = True

    def untaint (self):
        """ Sets the tainted flag to False """
        self._tainted = False

    def close (self):
        """
        Closes the underlaying service, so next call to the proxy will create a new
        instance of it.
        """
        
        if self._obj and isinstance(self._obj, omero.api.StatefulServiceInterfacePrx):
            self._obj.close()
        self._obj = None
    
    def _resyncConn (self, conn):
        """
        Reset refs to connection and session factory. Resets session creation function. 
        Attempts to reload the wrapped service - if already created (doesn't create service)
        
        @param conn:    Connection
        @type conn:     L{BlitzGateway}
        """
        
        self._conn = conn
        self._sf = conn.c.sf
        self._create_func = getattr(self._sf, self._func_str)
        if self._obj is not None:
            try:
                logger.debug("## - refreshing %s" % (self._func_str))
                obj = conn.c.ic.stringToProxy(str(self._obj))
                self._obj = self._obj.checkedCast(obj)
            except Ice.ObjectNotExistException:
                self._obj = None

    def _getObj (self):
        """
        Returns the wrapped service. If it is None, service is created. 
        
        @return:    The wrapped service
        @rtype:     omero.api.ServiceInterface subclass
        """
        
        if not self._obj:
            try:
                self._obj = self._create_func()
            except Ice.ConnectionLostException:
                logger.debug('... lost, reconnecting (_getObj)')
                self._connect()
                #self._obj = self._create_func()
        else:
            self._ping()
        return self._obj

    def _ping (self): #pragma: no cover
        """
        For some reason, it seems that keepAlive doesn't, so every so often I need to recreate the objects.
        Calls serviceFactory.keepAlive(service). If this returns false, attempt to create service. 
        
        @return:    True if no exception thrown 
        @rtype:     Boolean
        """
        
        try:
            if not self._sf.keepAlive(self._obj):
                logger.debug("... died, recreating ...")
                self._obj = self._create_func()
        except Ice.ObjectNotExistException:
            # The connection is there, but it has been reset, because the proxy no longer exists...
            logger.debug("... reset, reconnecting")
            self._connect()
            return False
        except Ice.ConnectionLostException:
            # The connection was lost. This shouldn't happen, as we keep pinging it, but does so...
            logger.debug(traceback.format_stack())
            logger.debug("... lost, reconnecting (_ping)")
            self._conn._connected = False
            self._connect()
            return False
        except Ice.ConnectionRefusedException:
            # The connection was refused. We lost contact with glacier2router...
            logger.debug(traceback.format_stack())
            logger.debug("... refused, reconnecting")
            self._connect()
            return False
        except omero.RemovedSessionException:
            # Session died on us
            logger.debug(traceback.format_stack())
            logger.debug("... session has left the building, reconnecting")
            self._connect()
            return False
        except Ice.UnknownException:
            # Probably a wrapped RemovedSession
            logger.debug(traceback.format_stack())
            logger.debug("... ice says something bad happened, reconnecting")
            self._connect()
            return False
        return True

    def __getattr__ (self, attr):
        """
        Returns named attribute of the wrapped service. 
        If attribute is a method, the method is wrapped to handle exceptions, connection etc.
        
        @param attr:    Attribute name
        @type attr:     String
        @return:        Attribute or wrapped method
        """
        # safe call wrapper
        obj = self._obj or self._getObj()
        rv = getattr(obj, attr)
        if callable(rv):
            rv = safeCallWrap(self, attr, rv)
        #self._conn.updateTimeout()
        return rv

class AnnotationWrapper (BlitzObjectWrapper):
    """
    omero_model_AnnotationI class wrapper extends BlitzObjectWrapper.
    """
    registry = {}       # class dict for type:wrapper E.g. DoubleAnnotationI : DoubleAnnotationWrapper
    OMERO_TYPE = None

    def __init__ (self, *args, **kwargs):
        """
        Initialises the Annotation wrapper and 'link' if in kwargs
        """
        super(AnnotationWrapper, self).__init__(*args, **kwargs)
        self.link = kwargs.has_key('link') and kwargs['link'] or None
        if self._obj is None and self.OMERO_TYPE is not None:
            self._obj = self.OMERO_TYPE()

    def __eq__ (self, a):
        """
        Returns true if type, id, value and ns are equal
        
        @param a:   The annotation to compare
        @return:    True if annotations are the same - see above
        @rtype:     Boolean
        """
        return type(a) == type(self) and self._obj.id == a._obj.id and self.getValue() == a.getValue() and self.getNs() == a.getNs()

    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("Annotation")
        """
        return "select obj from Annotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent"
        
    @classmethod
    def _register (klass, regklass):
        """
        Adds the AnnotationWrapper regklass to class registry
        @param regklass:    The wrapper class, E.g. L{DoubleAnnotationWrapper} 
        @type regklass:     L{AnnotationWrapper} subclass
        """
        
        klass.registry[regklass.OMERO_TYPE] = regklass

    @classmethod
    def _wrap (klass, conn=None, obj=None, link=None):
        """
        Class method for creating L{AnnotationWrapper} subclasses based on the type of 
        annotation object, using previously registered mapping between OMERO types and wrapper classes
        
        @param conn:    The L{BlitzGateway} connection
        @type conn:     L{BlitzGateway}
        @param obj:     The OMERO annotation object. E.g. omero.model.DoubleAnnotation
        @type obj:      L{omero.model.Annotation} subclass
        @param link:    The link for this annotation
        @type link:     E.g. omero.model.DatasetAnnotationLink
        @return:    Wrapped AnnotationWrapper object or None if obj.__class__ not registered
        @rtype:     L{AnnotationWrapper} subclass
        """
        if obj is None:
            return AnnotationWrapper()
        if obj.__class__ in klass.registry:
            kwargs = dict()
            if link is not None:
                kwargs['link'] = BlitzObjectWrapper(conn, link)
            return klass.registry[obj.__class__](conn, obj, **kwargs)
        else: #pragma: no cover
            return None

    @classmethod
    def createAndLink (klass, target, ns, val=None):
        """
        Class method for creating an instance of this AnnotationWrapper, setting ns and value
        and linking to the target. 
        
        @param target:      The object to link annotation to
        @type target:       L{BlitzObjectWrapper} subclass
        @param ns:          Annotation namespace
        @type ns:           String
        @param val:         Value of annotation. E.g Long, Text, Boolean etc. 
        """
        
        this = klass()
        this.setNs(ns)
        if val is not None:
            this.setValue(val)
        target.linkAnnotation(this)

    def getNs (self):
        """
        Gets annotation namespace
        
        @return:    Namespace or None
        @rtype:     String
        """
        
        return self._obj.ns is not None and self._obj.ns.val or None

    def setNs (self, val):
        """
        Sets annotation namespace
        
        @param val:     Namespace value
        @type val:      String
        """
        
        self._obj.ns = omero_type(val)
    
    def getValue (self): #pragma: no cover
        """ Needs to be implemented by subclasses """
        raise NotImplementedError

    def setValue (self, val): #pragma: no cover
        """ Needs to be implemented by subclasses """
        raise NotImplementedError
    
    def getParentLinks(self, ptype, pids=None): 
        ptype = ptype.lower()
        if not ptype in ('project', 'dataset', 'image', 'screen', 'plate', 'well'):
            AttributeError('Annotation can be linked only to: project, dataset, image, screen, plate, well')
        p = omero.sys.Parameters()
        p.map = {}
        p.map["aid"] = rlong(self.id)
        sql = "select oal from %sAnnotationLink as oal left outer join fetch oal.child as ch " \
                "left outer join fetch oal.parent as pa " \
                "where ch.id=:aid " % (ptype.title())
        if pids is not None:
            p.map["pids"] = rlist([rlong(ob) for ob in pids])
            sql+=" and pa.id in (:pids)" 
            
        for al in self._conn.getQueryService().findAllByQuery(sql, p):
            yield AnnotationLinkWrapper(self, al)

class _AnnotationLinkWrapper (BlitzObjectWrapper):
    """
    omero_model_AnnotationLinkI class wrapper extends omero.gateway.BlitzObjectWrapper.
    """

    def getAnnotation(self):
        return AnnotationWrapper._wrap(self._conn, self.child)

AnnotationLinkWrapper = _AnnotationLinkWrapper
                
from omero_model_FileAnnotationI import FileAnnotationI

class FileAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_FileAnnotatio class wrapper extends AnnotationWrapper.
    """

    OMERO_TYPE = FileAnnotationI

    def __loadedHotSwap__ (self):
        """
        Checks that the Annotation's File is loaded - Loads if needed. 
        """
        if not self._obj.file.loaded:
            self._obj._file = self._conn.getQueryService().find('OriginalFile', self._obj.file.id.val)

    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("FileAnnotation")
        """
        return "select obj from FileAnnotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent"

    def getValue (self):
        """ Not implemented """
        pass

    def setValue (self, val):
        """ Not implemented """
        pass

    def isOriginalMetadata(self):
        """
        Checks if this file annotation is an 'original_metadata' file
        
        @return:    True if namespace and file name follow metadata convention
        @rtype:     Boolean
        """
        
        self.__loadedHotSwap__()
        try:
            if self._obj.ns is not None and self._obj.ns.val == omero.constants.namespaces.NSCOMPANIONFILE and self._obj.file.name.val.startswith("original_metadata"):
                return True
        except:
            logger.info(traceback.format_exc())
        return False
     
    def getFileSize(self):
        """
        Looks up the size of the file in bytes
        
        @return:    File size (bytes)
        @rtype:     Long
        """
        
        return self._obj.file.size.val

    def getFileName(self):
        """
        Gets the file name
        
        @return:    File name
        @rtype:     String
        """
        
        self.__loadedHotSwap__()
        return self._obj.file.name.val
    
    def getFileInChunks(self):
        """
        Returns a generator yielding chunks of the file data. 
        
        @return:    Data from file in chunks
        @rtype:     Generator
        """
        
        self.__loadedHotSwap__()
        store = self._conn.createRawFileStore()
        store.setFileId(self._obj.file.id.val)
        size = self.getFileSize()
        buf = 2621440
        if size <= buf:
            yield store.read(0,long(size))
        else:
            for pos in range(0,long(size),buf):
                data = None
                if size-pos < buf:
                    data = store.read(pos, size-pos)
                else:
                    data = store.read(pos, buf)
                yield data
        store.close()


#    def shortTag(self):
#        if isinstance(self._obj, TagAnnotationI):
#            try:
#                name = self._obj.textValue.val
#                l = len(name)
#                if l < 25:
#                    return name
#                return name[:10] + "..." + name[l - 10:] 
#            except:
#                logger.info(traceback.format_exc())
#                return self._obj.textValue.val

AnnotationWrapper._register(FileAnnotationWrapper)


class _OriginalFileWrapper (BlitzObjectWrapper):
    """
    omero_model_OriginalFileI class wrapper extends BlitzObjectWrapper.
    """

    def __bstrap__ (self):
        self.OMERO_CLASS = 'OriginalFile'

    def getFileInChunks(self):
        """
        Returns a generator yielding chunks of the file data.

        @return:    Data from file in chunks
        @rtype:     Generator
        """

        if not self._obj.isLoaded():
            self._obj = self._conn.getQueryService().get(self.OMERO_CLASS, self._obj.id.val)
        store = self._conn.createRawFileStore()
        store.setFileId(self._obj.id.val)
        size = self._obj.size.val
        buf = 2621440
        if size <= buf:
            yield store.read(0,long(size))
        else:
            for pos in range(0,long(size),buf):
                data = None
                if size-pos < buf:
                    data = store.read(pos, size-pos)
                else:
                    data = store.read(pos, buf)
                yield data
        store.close()

OriginalFileWrapper = _OriginalFileWrapper

from omero_model_TimestampAnnotationI import TimestampAnnotationI

class TimestampAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_TimestampAnnotatio class wrapper extends AnnotationWrapper.
    """
    
    OMERO_TYPE = TimestampAnnotationI

    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("TimestampAnnotation")
        """
        return "select obj from TimestampAnnotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent"

    def getValue (self):
        """
        Returns a datetime object of the timestamp in seconds
        
        @return:    Timestamp value
        @rtype:     L{datetime}
        """
        
        return datetime.fromtimestamp(self._obj.timeValue.val / 1000.0)

    def setValue (self, val):
        """
        Sets the timestamp value
        
        @param val:     Timestamp value
        @type param:    L{datetime} OR L{omero.RTime} OR Long
        """
        
        if isinstance(val, datetime):
            self._obj.timeValue = rtime(long(time.mktime(val.timetuple())*1000))
        elif isinstance(val, omero.RTime):
            self._obj.timeValue = val
        else:
            self._obj.timeValue = rtime(long(val * 1000))

AnnotationWrapper._register(TimestampAnnotationWrapper)

from omero_model_BooleanAnnotationI import BooleanAnnotationI

class BooleanAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_BooleanAnnotationI class wrapper extends AnnotationWrapper.
    """
    
    OMERO_TYPE = BooleanAnnotationI

    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("BooleanAnnotation")
        """
        return "select obj from BooleanAnnotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent"

    def getValue (self):
        """
        Gets boolean value
        
        @return:    Value
        @rtype:     Boolean
        """
        return self._obj.boolValue.val

    def setValue (self, val):
        """
        Sets boolean value
        
        @param val:     Value
        @type val:      Boolean
        """
        
        self._obj.boolValue = rbool(not not val)

AnnotationWrapper._register(BooleanAnnotationWrapper)

from omero_model_TagAnnotationI import TagAnnotationI

class TagAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_BooleanAnnotationI class wrapper extends AnnotationWrapper.
    """
    
    OMERO_TYPE = TagAnnotationI

    def countTagsInTagset(self):
        # temp solution waiting for #5785
        if self.ns in (omero.constants.metadata.NSINSIGHTTAGSET):
            params = omero.sys.Parameters()
            params.map = {}
            params.map['tid'] = self._obj.id
            sql = "select tg from TagAnnotation tg "\
                "where exists ( select aal from AnnotationAnnotationLink as aal where aal.child=tg.id and aal.parent.id=:tid) "
             
            res = self._conn.getQueryService().findAllByQuery(sql, params)
            return res is not None and len(res) or 0
                
    def listTagsInTagset(self):
        # temp solution waiting for #5785  
        if self.ns in (omero.constants.metadata.NSINSIGHTTAGSET):
            params = omero.sys.Parameters()
            params.map = {}
            params.map["tid"] = rlong(self._obj.id)
            
            sql = "select tg from TagAnnotation tg "\
                "where exists ( select aal from AnnotationAnnotationLink as aal where aal.child.id=tg.id and aal.parent.id=:tid) "
            
            q = self._conn.getQueryService()
            for ann in q.findAllByQuery(sql, params):
                yield TagAnnotationWrapper(self._conn, ann)
    
    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("TagAnnotation")
        """
        return "select obj from TagAnnotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent"

    def getValue (self):
        """ 
        Gets the value of the Tag
        
        @return:    Value
        @type:      String
        """
        
        return self._obj.textValue.val

    def setValue (self, val):
        """
        Sets Tag value
        
        @param val:     Tag text value
        @type val:      String
        """
        
        self._obj.textValue = omero_type(val)
    
AnnotationWrapper._register(TagAnnotationWrapper)

from omero_model_CommentAnnotationI import CommentAnnotationI

class CommentAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_CommentAnnotationI class wrapper extends AnnotationWrapper.
    """
    
    OMERO_TYPE = CommentAnnotationI

    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("CommentAnnotation")
        """
        return "select obj from CommentAnnotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
            "join fetch obj.details.creationEvent"

    def getValue (self):
        """ 
        Gets the value of the Comment
        
        @return:    Value
        @type:      String
        """
        
        return self._obj.textValue.val

    def setValue (self, val):
        """
        Sets comment text value
        
        @param val:     Value
        @type val:      String
        """
        
        self._obj.textValue = omero_type(val)

AnnotationWrapper._register(CommentAnnotationWrapper)

from omero_model_LongAnnotationI import LongAnnotationI

class LongAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_LongAnnotationI class wrapper extends AnnotationWrapper.
    """
    OMERO_TYPE = LongAnnotationI

    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("LongAnnotation")
        """
        return "select obj from LongAnnotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent"

    def getValue (self):
        """ 
        Gets the value of the Long annotation
        
        @return:    Value
        @type:      Long
        """
        
        return self._obj.longValue and self._obj.longValue.val or None

    def setValue (self, val):
        """
        Sets long annotation value
        
        @param val:     Value
        @type val:      Long
        """
        
        self._obj.longValue = rlong(val)

AnnotationWrapper._register(LongAnnotationWrapper)

from omero_model_DoubleAnnotationI import DoubleAnnotationI

class DoubleAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_DoubleAnnotationI class wrapper extends AnnotationWrapper.
    """
    OMERO_TYPE = DoubleAnnotationI

    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("DoubleAnnotation")
        """
        return "select obj from DoubleAnnotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent"

    def getValue (self):
        """ 
        Gets the value of the Double Annotation
        
        @return:    Value
        @type:      Double
        """
        
        return self._obj.doubleValue.val

    def setValue (self, val):
        """
        Sets Double annotation value
        
        @param val:     Value
        @type val:      Double
        """
        
        self._obj.doubleValue = rdouble(val)

AnnotationWrapper._register(DoubleAnnotationWrapper)

from omero_model_TermAnnotationI import TermAnnotationI

class TermAnnotationWrapper (AnnotationWrapper):
    """
    omero_model_TermAnnotationI class wrapper extends AnnotationWrapper.

    only in 4.2+
    """
    OMERO_TYPE = TermAnnotationI

    def _getQueryString(self):
        """
        Used for building queries in generic methods such as getObjects("TermAnnotation")
        """
        return "select obj from TermAnnotation obj join fetch obj.details.owner as owner join fetch obj.details.group "\
                "join fetch obj.details.creationEvent"

    def getValue (self):
        """ 
        Gets the value of the Term
        
        @return:    Value
        @type:      String
        """
        
        return self._obj.termValue.val

    def setValue (self, val):
        """
        Sets term value
        
        @param val:     Value
        @type val:      String
        """
        
        self._obj.termValue = rstring(val)

AnnotationWrapper._register(TermAnnotationWrapper)

from omero_model_XmlAnnotationI import XmlAnnotationI

class XmlAnnotationWrapper (CommentAnnotationWrapper):
    """
    omero_model_XmlAnnotationI class wrapper extends CommentAnnotationWrapper.
    """
    OMERO_TYPE = XmlAnnotationI
    
AnnotationWrapper._register(XmlAnnotationWrapper)

class _EnumerationWrapper (BlitzObjectWrapper):
    
    def getType(self):
        """ 
        Gets the type (class) of the Enumeration
        
        @return:    The omero class
        @type:      Class
        """
        
        return self._obj.__class__

EnumerationWrapper = _EnumerationWrapper

class _ExperimenterWrapper (BlitzObjectWrapper):
    """
    omero_model_ExperimenterI class wrapper extends BlitzObjectWrapper.
    """

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Experimenter'
        self.LINK_CLASS = "GroupExperimenterMap"
        self.CHILD_WRAPPER_CLASS = None
        self.PARENT_WRAPPER_CLASS = 'ExperimenterGroupWrapper'

    def simpleMarshal (self, xtra=None, parents=False):
        rv = super(_ExperimenterWrapper, self).simpleMarshal(xtra=xtra, parents=parents)
        rv.update({'firstName': self.firstName,
                   'middleName': self.middleName,
                   'lastName': self.lastName,
                   'email': self.email,
                   'isAdmin': len(filter(lambda x: x.name.val == 'system', self._conn.getAdminService().containedGroups(self.getId()))) == 1,
                   })
        return rv

    def _getQueryString(self):
        """ 
        Returns string for building queries, loading Experimenters only. 
        """
        return "select distinct obj from Experimenter as obj"

    def getRawPreferences (self):
        """
        Returns the experimenter's preferences annotation contents, as a ConfigParser instance
        
        @return:    See above
        @rtype:     ConfigParser
        """
        
        self._obj.unloadAnnotationLinks()
        cp = ConfigParser.SafeConfigParser()
        prefs = self.getAnnotation('TODO.changeme.preferences')
        if prefs is not None:
            prefs = prefs.getValue()
            if prefs is not None:
                cp.readfp(StringIO(prefs))
        return cp

    def setRawPreferences (self, prefs):
        """
        Sets the experimenter's preferences annotation contents, passed in as a ConfigParser instance
        
        @param prefs:       ConfigParser of preferences
        @type prefs:        ConfigParser
        """
        
        ann = self.getAnnotation('TODO.changeme.preferences')
        t = StringIO()
        prefs.write(t)
        if ann is None:
            ann = CommentAnnotationWrapper()
            ann.setNs('TODO.changeme.preferences')
            ann.setValue(t.getvalue())
            self.linkAnnotation(ann)
        else:
            ann.setValue(t.getvalue())
            ann.save()
            self._obj.unloadAnnotationLinks()
    
    def getPreference (self, key, default='', section=None):
        """
        Gets a preference for the experimenter
        
        @param key:     Preference key
        @param default: Default value to return
        @param section: Preferences section
        @return:        Preference value
        """
        
        if section is None:
            section = 'DEFAULT'
        try:
            return self.getRawPreferences().get(section, key)
        except ConfigParser.Error:
            return default
        return default

    def getPreferences (self, section=None):
        """
        Gets all preferences for section
        
        @param section: Preferences section
        @return:        Dict of preferences
        """
        
        if section is None:
            section = 'DEFAULT'
        prefs = self.getRawPreferences()
        if prefs.has_section(section) or section == 'DEFAULT':
            return dict(prefs.items(section))
        return {}

    def setPreference (self, key, value, section=None):
        """
        Sets a preference for the experimenter
        
        @param key:     Preference key
        @param value:   Value to set
        @param section: Preferences section - created if needed
        """
        
        if section is None:
            section = 'DEFAULT'
        prefs = self.getRawPreferences()
        if not section in prefs.sections():
            prefs.add_section(section)
        prefs.set(section, key, value)
        self.setRawPreferences(prefs)

    def getDetails (self):
        """
        Make sure we have correct details for this experimenter and return them
        
        @return:    Experimenter Details
        @rtype:     L{DetailsWrapper}
        """
        
        if not self._obj.details.owner:
            details = omero.model.DetailsI()
            details.owner = self._obj
            self._obj._details = details
        return DetailsWrapper(self._conn, self._obj.details)

    def getName (self):
        """
        Returns Experimenter's omeName 
        
        @return:    Name
        @rtype:     String
        """
        
        return self.omeName

    def getDescription (self):
        """
        Returns Experimenter's Full Name 
        
        @return:    Full Name or None
        @rtype:     String
        """
        
        return self.getFullName()

    def getFullName (self):
        """
        Gets full name of this experimenter. E.g. 'William James. Moore' or 'William Moore' if no middle name
        
        @return:    Full Name or None
        @rtype:     String
        """
        
        try:
            lastName = self.lastName
            firstName = self.firstName
            middleName = self.middleName
            
            if middleName is not None and middleName != '':
                name = "%s %s. %s" % (firstName, middleName, lastName)
            else:
                name = "%s %s" % (firstName, lastName)
            return name
        except:
            logger.error(traceback.format_exc())
            return None
    
    def getNameWithInitial(self):
        """
        Returns first initial and Last name. E.g. 'W. Moore'
        
        @return:    Initial and last name
        @rtype:     String
        """
        
        try:
            if self.firstName is not None and self.lastName is not None:
                name = "%s. %s" % (self.firstName[:1], self.lastName)
            else:
                name = self.omeName
            return name
        except:
            logger.error(traceback.format_exc())
            return _("Unknown name")
    
    def isAdmin(self):
        """
        Returns true if Experimenter is Admin (if they are in any group named 'system')
        
        @return:    True if experimenter is Admin
        @rtype:     Boolean
        """
        
        for ob in self._obj.copyGroupExperimenterMap():
            if ob.parent.name.val == "system":
                return True
        return False
    
    def isActive(self):
        """
        Returns true if Experimenter is Active (if they are in any group named 'user')
        
        @return:    True if experimenter is Active
        @rtype:     Boolean
        """
        
        for ob in self._obj.copyGroupExperimenterMap():
            if ob.parent.name.val == "user":
                return True
        return False
    
    def isGuest(self):
        """
        Returns true if Experimenter is Guest (if they are in any group named 'guest')
        
        @return:    True if experimenter is Admin
        @rtype:     Boolean
        """
        
        for ob in self._obj.copyGroupExperimenterMap():
            if ob.parent.name.val == "guest":
                return True
        return False
    
ExperimenterWrapper = _ExperimenterWrapper

class _ExperimenterGroupWrapper (BlitzObjectWrapper):
    """
    omero_model_ExperimenterGroupI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'ExperimenterGroup'
        self.LINK_CLASS = "GroupExperimenterMap"
        self.CHILD_WRAPPER_CLASS = 'ExperimenterWrapper'
        self.PARENT_WRAPPER_CLASS = None

    def isLeader(self):
        """
        Is the current group led by the current user? 
        
        @return:    True if user leads the current group
        @rtype:     Boolean
        """
        if self._conn.getEventContext().groupId in self._conn.getEventContext().leaderOfGroups:
            return True
        return False
        
    def _getQueryString(self):
        """ 
        Returns string for building queries, loading Experimenters for each group. 
        """
        query = "select distinct obj from ExperimenterGroup as obj left outer join fetch obj.groupExperimenterMap " \
            "as map left outer join fetch map.child e"
        return query
        

ExperimenterGroupWrapper = _ExperimenterGroupWrapper

class DetailsWrapper (BlitzObjectWrapper):
    """
    omero_model_DetailsI class wrapper extends BlitzObjectWrapper.
    """
    
    def __init__ (self, *args, **kwargs):
        super(DetailsWrapper, self).__init__ (*args, **kwargs)
        owner = self._obj.getOwner()
        group = self._obj.getGroup()
        self._owner = owner and ExperimenterWrapper(self._conn, self._obj.getOwner()) or None
        self._group = group and ExperimenterGroupWrapper(self._conn, self._obj.getGroup()) or None

    def getOwner (self):
        """
        Returns the Owner of the object that these details apply to
        
        @return:    Owner
        @rtype:     L{ExperimenterWrapper}
        """
        
        return self._owner

    def getGroup (self):
        """
        Returns the Group that these details refer to
        
        @return:    Group
        @rtype:     L{ExperimenterGroupWrapper}
        """
        
        return self._group

class _DatasetWrapper (BlitzObjectWrapper):
    """
    omero_model_DatasetI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Dataset'
        self.LINK_CLASS = "DatasetImageLink"
        self.CHILD_WRAPPER_CLASS = 'ImageWrapper'
        self.PARENT_WRAPPER_CLASS = 'ProjectWrapper'

    def __loadedHotSwap__ (self):
        """ In addition to loading the Dataset, this method also loads the Images """
        
        super(_DatasetWrapper, self).__loadedHotSwap__()
        if not self._obj.isImageLinksLoaded():
            links = self._conn.getQueryService().findAllByQuery("select l from DatasetImageLink as l join fetch l.child as a where l.parent.id=%i" % (self._oid), None)
            self._obj._imageLinksLoaded = True
            self._obj._imageLinksSeq = links

DatasetWrapper = _DatasetWrapper

class _ProjectWrapper (BlitzObjectWrapper):
    """
    omero_model_ProjectI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Project'
        self.LINK_CLASS = "ProjectDatasetLink"
        self.CHILD_WRAPPER_CLASS = 'DatasetWrapper'
        self.PARENT_WRAPPER_CLASS = None

ProjectWrapper = _ProjectWrapper

class _ScreenWrapper (BlitzObjectWrapper):
    """
    omero_model_ScreenI class wrapper extends BlitzObjectWrapper.
    """
    
    annotation_counter = None
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Screen'
        self.LINK_CLASS = "ScreenPlateLink"
        self.CHILD_WRAPPER_CLASS = 'PlateWrapper'
        self.PARENT_WRAPPER_CLASS = None

ScreenWrapper = _ScreenWrapper

class _PlateWrapper (BlitzObjectWrapper):
    """
    omero_model_PlateI class wrapper extends BlitzObjectWrapper.
    """
    
    annotation_counter = None
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Plate'
        self.LINK_CLASS = None
        self.CHILD_WRAPPER_CLASS = None
        self.PARENT_WRAPPER_CLASS = 'ScreenWrapper'

    def _getQueryString(self):
        """
        Returns a query string for constructing custom queries, loading the screen for each plate.
        """
        query = "select obj from Plate obj join fetch obj.details.owner join fetch obj.details.group "\
              "join fetch obj.details.creationEvent "\
              "left outer join fetch obj.screenLinks spl " \
              "left outer join fetch spl.parent sc"
        return query

PlateWrapper = _PlateWrapper

class _WellWrapper (BlitzObjectWrapper):
    """
    omero_model_WellI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Well'
        self.LINK_CLASS = "WellSample"
        self.CHILD_WRAPPER_CLASS = "ImageWrapper"
        self.PARENT_WRAPPER_CLASS = 'PlateWrapper'
    
    def __prepare__ (self, **kwargs):
        try:
            self.index = int(kwargs['index'])
        except:
            self.index = 0
    
    def isWellSample (self):
        """ 
        Return True if well samples exist (loaded)
        
        @return:    True if well samples loaded
        @rtype:     Boolean
        """
        
        if getattr(self, 'isWellSamplesLoaded')():
            childnodes = getattr(self, 'copyWellSamples')()
            logger.debug('listChildren for %s %d: already loaded, %d samples' % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            if len(childnodes) > 0:
                return True
        return False
    
    def countWellSample (self):
        """
        Return the number of well samples loaded
        
        @return:    well sample count
        @rtype:     Int
        """
        
        if getattr(self, 'isWellSamplesLoaded')():
            childnodes = getattr(self, 'copyWellSamples')()
            logger.debug('countChildren for %s %d: already loaded, %d samples' % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            size = len(childnodes)
            if size > 0:
                return size
        return 0
    
    def selectedWellSample (self):
        """
        Return the well sample at the current index (0 if not set)
        
        @return:    The Well Sample wrapper
        @rtype:     L{WellSampleWrapper}
        
        """
        
        if getattr(self, 'isWellSamplesLoaded')():
            childnodes = getattr(self, 'copyWellSamples')()
            logger.debug('listSelectedChildren for %s %d: already loaded, %d samples' % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            if len(childnodes) > 0:
                return WellSampleWrapper(self._conn, childnodes[self.index])
        return None
    
    def loadWellSamples (self):
        """
        Return a generator yielding child objects
        
        @return:    Well Samples
        @rtype:     L{WellSampleWrapper} generator
        """
        
        if getattr(self, 'isWellSamplesLoaded')():
            childnodes = getattr(self, 'copyWellSamples')()
            logger.debug('listChildren for %s %d: already loaded, %d samples' % (self.OMERO_CLASS, self.getId(), len(childnodes)))
            for ch in childnodes:
                yield WellSampleWrapper(self._conn, ch)
    
    def plate(self):
        """
        Gets the Plate. 
        
        @return:    The Plate
        @rtype:     L{PlateWrapper}
        """
        
        return PlateWrapper(self._conn, self._obj.plate)

WellWrapper = _WellWrapper

class _WellSampleWrapper (BlitzObjectWrapper):
    """
    omero_model_WellSampleI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'WellSample'
        self.CHILD_WRAPPER_CLASS = "ImageWrapper"
        self.PARENT_WRAPPER_CLASS = 'WellWrapper'
        
    def image(self):
        """
        Gets the Image for this well sample.
        
        @return:    The Image
        @rtype:     L{ImageWrapper}
        """
        
        return ImageWrapper(self._conn, self._obj.image)

WellSampleWrapper = _WellSampleWrapper

#class CategoryWrapper (BlitzObjectWrapper):
#    def __bstrap__ (self):
#        self.LINK_CLASS = "CategoryImageLink"
#        self.CHILD_WRAPPER_CLASS = ImageWrapper
#        self.PARENT_WRAPPER_CLASS= 'CategoryGroupWrapper'
#
#class CategoryGroupWrapper (BlitzObjectWrapper):
#    def __bstrap__ (self):
#        self.LINK_CLASS = "CategoryGroupCategoryLink"
#        self.CHILD_WRAPPER_CLASS = CategoryWrapper
#        self.PARENT_WRAPPER_CLASS = None

## IMAGE ##

class ColorHolder (object):
    """
    Stores color internally as (R,G,B,A) and allows setting and getting in multiple formats
    """
    
    _color = {'red': 0, 'green': 0, 'blue': 0, 'alpha': 255}

    def __init__ (self, colorname=None):
        """
        If colorname is 'red', 'green' or 'blue', set color accordingly - Otherwise black
        
        @param colorname:   'red', 'green' or 'blue'
        @type colorname:    String
        """
        
        self._color = {'red': 0, 'green': 0, 'blue': 0, 'alpha': 255}
        if colorname and colorname.lower() in self._color.keys():
            self._color[colorname.lower()] = 255

    @classmethod
    def fromRGBA(klass,r,g,b,a):
        """
        Class method for creating a ColorHolder from r,g,b,a values
        
        @param r:   red 0 - 255
        @type r:    int
        @param g:   green 0 - 255
        @type g:    int
        @param b:   blue 0 - 255
        @type b:    int
        @param a:   alpha 0 - 255
        @type a:    int
        @return:    new Color object
        @rtype:     L{ColorHolder}
        """
        
        rv = klass()
        rv.setRed(r)
        rv.setGreen(g)
        rv.setBlue(b)
        rv.setAlpha(a)
        return rv

    def getRed (self):
        """
        Gets the Red component
        
        @return:    red
        @rtype:     int
        """
        
        return self._color['red']

    def setRed (self, val):
        """
        Set red, as int 0..255 
        
        @param val: value of Red.
        @type val:  Int
        """
        
        self._color['red'] = max(min(255, int(val)), 0)

    def getGreen (self):
        """
        Gets the Green component
        
        @return:    green
        @rtype:     int
        """
        
        return self._color['green']

    def setGreen (self, val):
        """
        Set green, as int 0..255 
        
        @param val: value of Green.
        @type val:  Int
        """
        
        self._color['green'] = max(min(255, int(val)), 0)

    def getBlue (self):
        """
        Gets the Blue component
        
        @return:    blue
        @rtype:     int
        """
        
        return self._color['blue']

    def setBlue (self, val):
        """
        Set Blue, as int 0..255 
        
        @param val: value of Blue.
        @type val:  Int
        """
        
        self._color['blue'] = max(min(255, int(val)), 0)

    def getAlpha (self):
        """
        Gets the Alpha component
        
        @return:    alpha
        @rtype:     int
        """
        
        return self._color['alpha']

    def setAlpha (self, val):
        """
        Set alpha, as int 0..255.
        @param val: value of alpha.
        """
        
        self._color['alpha'] = max(min(255, int(val)), 0)

    def getHtml (self):
        """
        Gets the html usable color. Dumps the alpha information. E.g. 'FF0000'
        
        @return:    html color
        @rtype:     String
        """
        
        return "%(red)0.2X%(green)0.2X%(blue)0.2X" % (self._color)

    def getCss (self):
        """
        Gets the css string: rgba(r,g,b,a)
        
        @return:    css color
        @rtype:     String
        """
        
        c = self._color.copy()
        c['alpha'] /= 255.0
        return "rgba(%(red)i,%(green)i,%(blue)i,%(alpha)0.3f)" % (c)

    def getRGB (self):
        """
        Gets the (r,g,b) as a tuple. 
        
        @return:    Tuple of (r,g,b) values
        @rtype:     tuple of ints
        """
        
        return (self._color['red'], self._color['green'], self._color['blue'])

class _LogicalChannelWrapper (BlitzObjectWrapper):
    """
    omero_model_LogicalChannelI class wrapper extends BlitzObjectWrapper.
    Specifies a number of _attrs for the channel metadata.
    """
    _attrs = ('name',
              'pinHoleSize',
              '#illumination',
              'contrastMethod',
              'excitationWave',
              'emissionWave',
              'fluor',
              'ndFilter',
              'otf',
              'detectorSettings|DetectorSettingsWrapper',
              'lightSourceSettings|LightSettingsWrapper',
              'filterSet|FilterSetWrapper',
              'secondaryEmissionFilter|FilterWrapper',
              'secondaryExcitationFilter',
              'samplesPerPixel',
              '#photometricInterpretation',
              'mode',
              'pockelCellSetting',
              'shapes',
              'version')

    def __loadedHotSwap__ (self):
        """ Loads the logical channel using the metadata service """
        if self._obj is not None:
            self._obj = self._conn.getMetadataService().loadChannelAcquisitionData([self._obj.id.val])[0]

    def getLightPath(self):
        """ Make sure we have the channel fully loaded, then return L{LightPathWrapper}"""
        self.__loadedHotSwap__()
        if self._obj.lightPath is not None:
            return LightPathWrapper(self._conn, self._obj.lightPath)

LogicalChannelWrapper = _LogicalChannelWrapper    

class _LightPathWrapper (BlitzObjectWrapper):
    """
    base Light Source class wrapper, extends BlitzObjectWrapper.
    """
    _attrs = ('dichroic|DichroicWrapper',)
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'LightPath'

    def copyExcitationFilters(self):
        """ Returns list of excitation L{FilterWrapper}s """
        return [FilterWrapper(self._conn, link.child) for link in self.copyExcitationFilterLink()]

    def copyEmissionFilters(self):
        """ Returns list of emission L{FilterWrapper}s """
        return [FilterWrapper(self._conn, link.child) for link in self.copyEmissionFilterLink()]

LightPathWrapper = _LightPathWrapper

class _PixelsWrapper (BlitzObjectWrapper):
    """
    omero_model_PixelsI class wrapper extends BlitzObjectWrapper.
    """
    
    def __bstrap__ (self):
        self.OMERO_CLASS = 'Pixels'

    def _prepareRawPixelsStore(self):
        """
        Creates RawPixelsStore and sets the id etc
        """
        ps = self._conn.createRawPixelsStore()
        ps.setPixelsId(self._obj.id.val, True)
        return ps

    def getPixelsType (self):
        """
        This simply wraps the PixelsType object in a BlitzObjectWrapper.
        Shouldn't be needed when this is done automatically
        """
        return BlitzObjectWrapper(self._conn, self._obj.getPixelsType())

    def copyPlaneInfo (self, theC=None, theT=None, theZ=None):
        """ 
        Loads plane infos and returns sequence of omero.model.PlaneInfo objects wrapped in BlitzObjectWrappers 
        ordered by planeInfo.deltaT.
        Set of plane infos can be filtered by C, T or Z

        @param theC:    Filter plane infos by Channel index
        @param theT:    Filter plane infos by Time index
        @param theZ:    Filter plane infos by Z index
        """

        params = omero.sys.Parameters()
        params.map = {}
        params.map["pid"] = rlong(self._obj.id)
        query = "select info from PlaneInfo as info where pixels.id=:pid"
        if theC != None:
            params.map["theC"] = rint(theC)
            query += " and info.theC=:theC"
        if theT != None:
            params.map["theT"] = rint(theT)
            query += " and info.theT=:theT"
        if theZ != None:
            params.map["theZ"] = rint(theZ)
            query += " and info.theZ=:theZ"
        query += " order by info.deltaT"
        queryService = self._conn.getQueryService()
        result = queryService.findAllByQuery(query, params)
        for pi in result:
            yield BlitzObjectWrapper(self._conn, pi)

    def getPlanes (self, zctList):
        """
        Returns generator of numpy 2D planes from this set of pixels for a list of Z, C, T indexes.

        @param zctList:     A list of indexes: [(z,c,t), ]
        """
        
        zctTileList = []
        for zct in zctList:
            z,c,t = zct
            zctTileList.append((z,c,t, None))
        return self.getTiles(zctTileList)

    def getPlane (self, theZ=0, theC=0, theT=0):
        """
        Gets the specified plane as a 2D numpy array by calling L{getPlanes}
        If a range of planes are required, L{getPlanes} is approximately 30% faster.
        """
        planeList = list( self.getPlanes([(theZ, theC, theT)]) )
        return planeList[0]

    def getTiles (self, zctTileList):
        """
        Returns generator of numpy 2D planes from this set of pixels for a list of (Z, C, T, tile)
        where tile is (x, y, width, height) or None if you want the whole plane.

        @param zctrList:     A list of indexes: [(z,c,t, region), ]
        """

        import numpy
        from struct import unpack

        pixelTypes = {"int8":['b',numpy.int8],
                "uint8":['B',numpy.uint8],
                "int16":['h',numpy.int16],
                "uint16":['H',numpy.uint16],
                "int32":['i',numpy.int32],
                "uint32":['I',numpy.uint32],
                "float":['f',numpy.float],
                "double":['d', numpy.double]}

        rawPixelsStore = self._prepareRawPixelsStore()
        sizeX = self.sizeX
        sizeY = self.sizeY
        pixelType = self.getPixelsType().value
        numpyType = pixelTypes[pixelType][1]
        exc = None
        try:
            for zctTile in zctTileList:
                z,c,t,tile = zctTile
                if tile is None:
                    rawPlane = rawPixelsStore.getPlane(z, c, t)
                    planeY = sizeY
                    planeX = sizeX
                else:
                    x, y, width, height = tile
                    rawPlane = rawPixelsStore.getTile(z, c, t, x, y, width, height)
                    planeY = height
                    planeX = width
                convertType ='>%d%s' % ((planeY*planeX), pixelTypes[pixelType][0])  #+str(sizeX*sizeY)+pythonTypes[pixelType]
                convertedPlane = unpack(convertType, rawPlane)
                remappedPlane = numpy.array(convertedPlane, numpyType)
                remappedPlane.resize(planeY, planeX)
                yield remappedPlane
        except Exception, e:
            logger.error("Failed to getPlane() or getTile() from rawPixelsStore", exc_info=True)
            exc = e
        try:
            rawPixelsStore.close()
        except Exception, e:
            logger.error("Failed to close rawPixelsStore", exc_info=True)
            if exc is None:
                 exc = e
        if exc is not None:
           raise exc

    def getTile (self, theZ=0, theC=0, theT=0, tile=None):
        """
        Gets the specified plane as a 2D numpy array by calling L{getPlanes}
        If a range of tile are required, L{getTiles} is approximately 30% faster.
        """
        tileList = list( self.getTiles([(theZ, theC, theT, tile)]) )
        return tileList[0]

PixelsWrapper = _PixelsWrapper


class _ChannelWrapper (BlitzObjectWrapper):
    """
    omero_model_ChannelI class wrapper extends BlitzObjectWrapper.
    """
    
    BLUE_MIN = 400
    BLUE_MAX = 500
    GREEN_MIN = 501
    GREEN_MAX = 600
    RED_MIN = 601
    RED_MAX = 700
    COLOR_MAP = ((BLUE_MIN, BLUE_MAX, ColorHolder('Blue')),
                 (GREEN_MIN, GREEN_MAX, ColorHolder('Green')),
                 (RED_MIN, RED_MAX, ColorHolder('Red')),
                 )

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Channel'

    def __prepare__ (self, idx=-1, re=None, img=None):
        """
        Sets values of idx, re and img
        """
        self._re = re
        self._idx = idx
        self._img = img

    def save (self):
        """
        Extends the superclass save method to save Pixels. Returns result of saving superclass (TODO: currently this is None)
        """
        
        self._obj.setPixels(omero.model.PixelsI(self._obj.getPixels().getId(), False))
        return super(_ChannelWrapper, self).save()

    def isActive (self):
        """
        Returns True if the channel is active (turned on in rendering settings)
        
        @return:    True if Channel is Active
        @rtype:     Boolean
        """
        
        if self._re is None:
            return False
        return self._re.isActive(self._idx)

    def getLogicalChannel (self):
        """
        Returns the logical channel
        
        @return:    Logical Channel
        @rtype:     L{LogicalChannelWrapper}
        """
        
        if self._obj.logicalChannel is not None:
            return LogicalChannelWrapper(self._conn, self._obj.logicalChannel)

    def getLabel (self):
        """
        Returns the logical channel name, emission wave or index. The first that is not null
        in the described order.

        @return:    The logical channel string representation
        @rtype:     String
        """

        lc = self.getLogicalChannel()
        rv = lc.name
        if rv is None:
            rv = lc.emissionWave
        if rv is None:
            rv = self._idx
        return unicode(rv)


    def getName (self):
        """
        Returns the logical channel name or None

        @return:    The logical channel string representation
        @rtype:     String
        """
        
        lc = self.getLogicalChannel()
        rv = lc.name
        if rv is not None:
            return unicode(rv)


    def getEmissionWave (self):
        """
        Returns the emission wave or None.

        @return:    Emission wavelength or None
        @rtype:     int
        """

        lc = self.getLogicalChannel()
        return lc.emissionWave

    def getExcitationWave (self):
        """
        Returns the excitation wave or None.

        @return:    Excitation wavelength or None
        @rtype:     int
        """

        lc = self.getLogicalChannel()
        return lc.excitationWave

    def getColor (self):
        """
        Returns the rendering settings color of this channel
        
        @return:    Channel color
        @rtype:     L{ColorHolder}
        """
        
        if self._re is None:
            return None
        return ColorHolder.fromRGBA(*self._re.getRGBA(self._idx))

    def getWindowStart (self):
        """
        Returns the rendering settings window-start of this channel
        
        @return:    Window start
        @rtype:     int
        """
        
        return int(self._re.getChannelWindowStart(self._idx))

    def setWindowStart (self, val):
        self.setWindow(val, self.getWindowEnd())

    def getWindowEnd (self):
        """
        Returns the rendering settings window-end of this channel
        
        @return:    Window end
        @rtype:     int
        """
        
        return int(self._re.getChannelWindowEnd(self._idx))

    def setWindowEnd (self, val):
        self.setWindow(self.getWindowStart(), val)

    def setWindow (self, minval, maxval):
        self._re.setChannelWindow(self._idx, float(minval), float(maxval))

    def getWindowMin (self):
        """
        Returns the minimum pixel value of the channel
        
        @return:    Min pixel value
        @rtype:     double
        """
        
        return self._obj.getStatsInfo().getGlobalMin().val

    def getWindowMax (self):
        """
        Returns the maximum pixel value of the channel
        
        @return:    Min pixel value
        @rtype:     double
        """
        
        return self._obj.getStatsInfo().getGlobalMax().val

ChannelWrapper = _ChannelWrapper

def assert_re (func):
    """
    Function decorator to make sure that rendering engine is prepared before call
    
    @param func:    Function
    @type func:     Function
    @return:        Decorated function
    @rtype:         Function
    """
    
    def wrapped (self, *args, **kwargs):
        """ Tries to prepare rendering engine, then call function and return the result"""
        try:
            if not self._prepareRenderingEngine():
                return None
        # _prepareRenderingEngine() may throw, but we ignore it
        except omero.ConcurrencyException, ce:
            pass
        return func(self, *args, **kwargs)
    return wrapped

def assert_pixels (func):
    """
    Function decorator to make sure that pixels are loaded before call
    
    @param func:    Function
    @type func:     Function
    @return:        Decorated function
    @rtype:         Function
    """
    
    def wrapped (self, *args, **kwargs):
        """ Tries to load pixels, then call function and return the result"""
        
        if not self._loadPixels():
            return None
        return func(self, *args, **kwargs)
    return wrapped


class _ImageWrapper (BlitzObjectWrapper):
    """
    omero_model_ImageI class wrapper extends BlitzObjectWrapper.
    """
    
    _re = None
    _pd = None
    _rm = {}
    _pixels = None

    _pr = None # projection

    _invertedAxis = False

    PROJECTIONS = {
        'normal': -1,
        'intmax': omero.constants.projection.ProjectionType.MAXIMUMINTENSITY,
        'intmean': omero.constants.projection.ProjectionType.MEANINTENSITY,
        'intsum': omero.constants.projection.ProjectionType.SUMINTENSITY,
        }
    
    PLANEDEF = omero.romio.XY

    @classmethod
    def fromPixelsId (self, conn, pid):
        """
        Creates a new Image wrapper with the image specified by pixels ID
        
        @param conn:    The connection
        @type conn:     L{BlitzGateway}
        @param pid:     Pixles ID
        @type pid:      Long
        @return:        New Image wrapper
        @rtype:         L{ImageWrapper}
        """
        
        q = conn.getQueryService()
        p = q.find('Pixels', pid)
        if p is None:
            return None
        return ImageWrapper(conn, p.image)

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Image'
        self.LINK_CLASS = None
        self.CHILD_WRAPPER_CLASS = None
        self.PARENT_WRAPPER_CLASS = 'DatasetWrapper'

    def __del__ (self):
        self._re and self._re.untaint()

    def __loadedHotSwap__ (self):
        self._obj = self._conn.getContainerService().getImages(self.OMERO_CLASS, (self._oid,), None)[0]
    
    def getInstrument (self):
        """
        Returns the Instrument for this image (or None) making sure the instrument is loaded. 
        
        @return:    Instrument (microscope)
        @rtype:     L{InstrumentWrapper}
        """
        
        i = self._obj.instrument
        if i is None:
            return None
        if not i.loaded:
            self._obj.instrument = self._conn.getQueryService().find('Instrument', i.id.val)
            i = self._obj.instrument
            meta_serv = self._conn.getMetadataService()
            instruments = meta_serv.loadInstrument(i.id.val)

            if instruments._detectorLoaded:
                i._detectorSeq.extend(instruments._detectorSeq)
            if instruments._objectiveLoaded:
                i._objectiveSeq.extend(instruments._objectiveSeq)
            if instruments._lightSourceLoaded:
                i._lightSourceSeq.extend(instruments._lightSourceSeq)
            if instruments._filterLoaded:
                i._filterSeq.extend(instruments._filterSeq)
            if instruments._dichroicLoaded:
                i._dichroicSeq.extend(instruments._dichroicSeq)
            if instruments._filterSetLoaded:
                i._filterSetSeq.extend(instruments._filterSetSeq)
            if instruments._otfLoaded:
                i._otfSeq.extend(instruments._otfSeq)
                    
        return InstrumentWrapper(self._conn, i)

    def _loadPixels (self):
        """
        Checks that pixels are loaded
        
        @return:    True if loaded
        @rtype:     Boolean
        """
        
        if not self._obj.pixelsLoaded:
            self.__loadedHotSwap__()
        return self._obj.sizeOfPixels() > 0


    def _getRDef (self, pid):
        """
        Return a rendering def ID based on custom logic.
        
        @param pid:         Pixels ID
        @type pid:          Long
        @return:            Rendering definition ID or None if no custom
                            logic has found a rendering definition.
        """
        rdefns = self._conn.CONFIG.get('IMG_RDEFNS', None)
        if rdefns is None:
            return
        rdid = ann.getValue()
        if rdid is None:
            return
        logger.debug('_getRDef: %s, %s' % (str(pid), str(rdid)))
        logger.debug('now load render options: %s' % str(self._loadRenderOptions()))
        self.loadRenderOptions()
        return rdid

    def _onResetDefaults(self, pid, rdid):
        """
        Called whenever a reset defaults is called by the preparation of
        the rendering engine or the thumbnail bean.
        
        @param pid:         Pixels ID
        @type pid:          Long
        @param pid:         Current Rendering Def ID
        @type pid:          Long
        """
        rdefns = self._conn.CONFIG.get('IMG_RDEFNS', None)
        if rdefns is None:
            return
        ann = self.getAnnotation(rdefns)
        if ann is None:
            a = LongAnnotationWrapper(self)
            a.setNs(rdefns)
            a.setValue(rdid)
            self.linkAnnotation(a, sameOwner=False)

    def _prepareRE (self):
        """
        Prepare the rendering engine with pixels ID and existing or new rendering def. 
        
        @return:            The Rendering Engine service
        @rtype:             L{ProxyObjectWrapper}
        """
        
        pid = self.getPrimaryPixels().id
        re = self._conn.createRenderingEngine()
        re.lookupPixels(pid)
        rdid = self._getRDef(pid)
        if rdid is None:
            if not re.lookupRenderingDef(pid):
                re.resetDefaults()
                re.lookupRenderingDef(pid)
                self._onResetDefaults(pid, re.getRenderingDefId())
        else:
            re.loadRenderingDef(rdid)
        re.load()
        return re

    def _prepareRenderingEngine (self):
        """
        Checks that the rendering engine is prepared, calling L{_prepareRE} if needed.
        Used by the L{assert_re} method to wrap calls requiring rendering engine
        
        @return:    True if rendering engine is created
        @rtype:     Boolean
        """
        
        try:
            self._loadPixels()
            if self._re is None:
                if self._obj.sizeOfPixels() < 1:
                    return False
                if self._pd is None:
                    self._pd = omero.romio.PlaneDef(self.PLANEDEF)
                self._re = self._prepareRE()
            return self._re is not None
        # allow others to handle ConcurrencyException- display Message etc.
        except omero.ConcurrencyException, ce:
            raise ce
        except:
            return None

    def resetRDefs (self):
        logger.debug('resetRDefs')
        if self.canWrite():
            self._conn.getDeleteService().deleteSettings(self.getId())
            return True
        return False

    def simpleMarshal (self, xtra=None, parents=False):
        """
        Creates a dict representation of the Image, including author and date info. 
        
        @return:    Dict
        @rtype:     Dict
        """
        
        rv = super(_ImageWrapper, self).simpleMarshal(xtra=xtra, parents=parents)
        rv.update({'author': self.getAuthor(),
                   'date': time.mktime(self.getDate().timetuple()),})
        if xtra:
            if xtra.has_key('thumbUrlPrefix'):
                if callable(xtra['thumbUrlPrefix']):
                    rv['thumb_url'] = xtra['thumbUrlPrefix'](str(self.id))
                else:
                    rv['thumb_url'] = xtra['thumbUrlPrefix'] + str(self.id) + '/'
        return rv

    def getStageLabel (self):
        """
        Returns the stage label or None
        
        @return:    Stage label
        @rtype:     L{ImageStageLabelWrapper}
        """
        
        if self._obj.stageLabel is None:
            return None
        else:
            return ImageStageLabelWrapper(self._conn, self._obj.stageLabel)
    
    def shortname(self, length=20, hist=5):
        """
        Provides a truncated name of the image. E.g. ...catedNameOfTheImage.tiff
        
        @param length:  The ideal length to return. If truncated, will be ...length
        @type length:   Int
        @param hist:    The amount of leeway allowed before trunction (avoid truncating 1 or 2 letters)
        @type hist:     Int
        @return:        Truncated ...name
        @type:          String
        """
        
        name = self.name
        if not name:
            return ""
        l = len(name)
        if l < length+hist:
            return name
        return "..." + name[l - length:]

    def getAuthor(self):
        """
        Returns 'Firstname Lastname' of image owner
        
        @return:    Image owner
        @rtype:     String
        """
        
        q = self._conn.getQueryService()
        e = q.findByQuery("select e from Experimenter e where e.id = %i" % self._obj.details.owner.id.val,None)
        self._author = e.firstName.val + " " + e.lastName.val
        return self._author

    def getDataset(self):
        """
        Gets the Dataset that image is in, or None. TODO: Why not use getParent()? 
        Returns None if Image is in more than one Dataset. 
        
        @return:    Dataset
        @rtype:     L{DatasetWrapper}
        """
        
        try:
            q = """
            select ds from Image i join i.datasetLinks dl join dl.parent ds
            where i.id = %i
            """ % self._obj.id.val
            query = self._conn.getQueryService()
            ds = query.findByQuery(q,None)
            return ds and DatasetWrapper(self._conn, ds) or None
        except: #pragma: no cover
            logger.debug('on getDataset')
            logger.debug(traceback.format_exc())
            return None
        
    def getProject(self):
        """
        Gets the Project that image is in, or None. TODO: Assumes image is in only 1 Project. Why not use getAncestory()[-1]
        Returns None if Image is in more than one Dataset & Project. 
        
        @return:    Project
        @rtype:     L{ProjectWrapper}
        """
        
        try:
            q = """
            select p from Image i join i.datasetLinks dl join dl.parent ds join ds.projectLinks pl join pl.parent p
            where i.id = %i
            """ % self._obj.id.val
            query = self._conn.getQueryService()
            prj = query.findByQuery(q,None)
            return prj and ProjectWrapper(self._conn, prj) or None
        except: #pragma: no cover
            logger.debug('on getProject')
            logger.debug(traceback.format_exc())
            return None

    def getObjectiveSettings (self):
        """
        Gets the Ojbective Settings of the Image, or None
        
        @return:    Objective Settings
        @rtype:     L{ObjectiveSettingsWrapper}
        """
        
        rv = self.objectiveSettings
        if self.objectiveSettings is not None:
            rv = ObjectiveSettingsWrapper(self._conn, self.objectiveSettings)
            if not self.objectiveSettings.loaded:
                self.objectiveSettings = rv._obj
        return rv

    def getImagingEnvironment (self):
        """
        Gets the Imaging Environment of the Image, or None
        
        @return:    Imaging Environment
        @rtype:     L{ImagingEnvironmentWrapper}
        """
        
        rv = self.imagingEnvironment
        if self.imagingEnvironment is not None:
            rv = ImagingEnvironmentWrapper(self._conn, self.imagingEnvironment)
            if not self.imagingEnvironment.loaded:
                self.imagingEnvironment = rv._obj
        return rv

    @assert_pixels
    def getPixelsId (self):
        """
        Returns the Primary Pixels ID for the image.
        
        @return:    Pixels ID
        @rtype:     Long
        """
        
        return self._obj.getPrimaryPixels().getId().val

    def _prepareTB (self, _r=False):
        """
        Prepares Thumbnail Store for the image.
        
        @param _r:          If True, don't reset default rendering (return None if no rDef exists)
        @type _r:           Boolean
        @return:            Thumbnail Store or None
        @rtype:             L{ProxyObjectWrapper}
        """
        
        pid = self.getPrimaryPixels().id
        tb = self._conn.createThumbnailStore()
        rdid = self._getRDef(pid)
        has_rendering_settings = tb.setPixelsId(pid)
        if rdid is None:
            if not has_rendering_settings:
                try:
                    tb.resetDefaults()      # E.g. May throw Missing Pyramid Exception
                except omero.ConcurrencyException, ce:
                    logger.info( "ConcurrencyException: resetDefaults() failed in _prepareTB with backOff: %s" % ce.backOff)
                    return tb
                tb.setPixelsId(pid)
                try:
                    rdid = tb.getRenderingDefId()
                except omero.ApiUsageException:         # E.g. No rendering def (because of missing pyramid!)
                    logger.info( "ApiUsageException: getRenderingDefId() failed in _prepareTB")
                    return tb
                self._onResetDefaults(pid, rdid)
        else:
            tb.setRenderingDefId(rdid)
        return tb

    def loadOriginalMetadata(self):
        """
        Gets original metadata from the file annotation. 
        Returns the File Annotation, list of Global Metadata, list of Series Metadata in a tuple. 
        Metadata lists are lists of (key, value) tuples. 
        
        @return:    Tuple of (file-annotation, global-metadata, series-metadata)
        @rtype:     Tuple (L{FileAnnotationWrapper}, [], [])
        """
        
        global_metadata = list()
        series_metadata = list()
        if self is not None:
            for a in self.listAnnotations():
                if isinstance(a._obj, FileAnnotationI) and a.isOriginalMetadata():
                    t_file = list()
                    for piece in a.getFileInChunks():
                        t_file.append(piece)
                    temp_file = "".join(t_file).split('\n')
                    flag = None
                    for l in temp_file:
                        if l.startswith("[GlobalMetadata]"):
                            flag = 1
                        elif l.startswith("[SeriesMetadata]"):
                            flag = 2
                        else:
                            if len(l) < 1:
                                l = None
                            else:
                                l = tuple(l.split("="))                            
                            if l is not None:
                                if flag == 1:
                                    global_metadata.append(l)
                                elif flag == 2:
                                    series_metadata.append(l)
                    return (a, (global_metadata), (series_metadata))
        return None

    @assert_re
    def _getProjectedThumbnail (self, size, pos):
        """
        Returns a string holding a rendered JPEG of the projected image, sized to mimic a thumbnail.
        This is an 'internal' method of this class, used to generate a thumbnail from a full-sized 
        projected image (since thumbnails don't support projection). SetProjection should be called 
        before this method is called, so that this returns a projected, scaled image.
        
        @param size:    The length of the longest size, in a list or tuple. E.g. (100,)
        @type size:     list or tuple
        @param pos:     The (z, t) position
        @type pos:      Tuple (z,t)
        """
        
        if pos is None:
            t = z = None
        else:
            z, t = pos
        img = self.renderImage(z,t)
        if len(size) == 1:
            w = self.getSizeX()
            h = self.getSizeY()
            ratio = float(w) / h
            if ratio > 1:
                h = h * size[0] / w
                w = size[0]
            else:
                w = w * size[0] / h
                h = size[0]
        img = img.resize((w,h), Image.NEAREST)
        rv = StringIO()
        img.save(rv, 'jpeg', quality=70)
        return rv.getvalue()

    def getThumbnail (self, size=(64,64), z=None, t=None):
        """
        Returns a string holding a rendered JPEG of the thumbnail.

        @type size: tuple or number
        @param size: A tuple with one or two ints, or an integer. If a tuple holding a single int,
                     or a single int is passed as param, then that will be used as the longest size
                     on the rendered thumb, and image aspect ratio is kept.
                     If two ints are passed in a tuple, they set the width and height of the
                     rendered thumb.
        @type z: number
        @param z: the Z position to use for rendering the thumbnail. If not provided default is used.
        @type t: number
        @param t: the T position to use for rendering the thumbnail. If not provided default is used.
        @rtype: string or None
        @return: the rendered JPEG, or None if there was an error.
        """
        tb = None
        try:
            tb = self._prepareTB()
            if tb is None:
                return None
            if isinstance(size, IntType):
                size = (size,)
            if z is not None and t is not None:
                pos = z,t
            else:
                pos = None
                # The following was commented out in the context of
                # omero:#5191. Preparing the rendering engine has the
                # potential to cause the raising of ConcurrencyException's
                # which prevent OMERO.web from executing the thumbnail methods
                # below and consequently showing "in-progress" thumbnails.
                # Tue 24 May 2011 10:42:47 BST -- cxallan
                #re = self._prepareRE()
                #if re:
                #    if z is None:
                #        z = re.getDefaultZ()
                #    if t is None:
                #        t = re.getDefaultT()
                #    pos = z,t
                #else:
                #    pos = None
            if self.getProjection() != 'normal':
                return self._getProjectedThumbnail(size, pos)
            if len(size) == 1:
                if pos is None:
                    thumb = tb.getThumbnailByLongestSideDirect
                else:
                    thumb = tb.getThumbnailForSectionByLongestSideDirect
            else:
                if pos is None:
                    thumb = tb.getThumbnailDirect
                else:
                    thumb = tb.getThumbnailForSectionDirect
            args = map(lambda x: rint(x), size)
            if pos is not None:
                args = list(pos) + args
            rv = thumb(*args)
            return rv
        except Exception: #pragma: no cover
            logger.error(traceback.format_exc())
            if tb is not None:
                tb.close()
            return None

    @assert_pixels
    def getPixelRange (self):
        """ 
        Returns (min, max) values for the pixels type of this image.
        TODO: Does not handle floats correctly, though.
        
        @return:    Tuple (min, max)
        """
        
        pixels_id = self._obj.getPrimaryPixels().getId().val
        rp = self._conn.createRawPixelsStore()
        rp.setPixelsId(pixels_id, True)
        pmax = 2 ** (8 * rp.getByteWidth())
        if rp.isSigned():
            return (-(pmax / 2), pmax / 2 - 1)
        else:
            return (0, pmax-1)

    @assert_pixels
    def getPrimaryPixels (self):
        """
        Loads pixels and returns object in a L{PixelsWrapper}
        """
        return PixelsWrapper(self._conn, self._obj.getPrimaryPixels())

    @assert_re
    def getChannels (self):
        """
        Returns a list of Channels, each initialised with rendering engine
        
        @return:    Channels
        @rtype:     List of L{ChannelWrapper}
        """
        if self._re is not None:
            return [ChannelWrapper(self._conn, c, idx=n, re=self._re, img=self) for n,c in enumerate(self._re.getPixels().iterateChannels())]
        else:       # E.g. ConcurrencyException (no rendering engine): load channels by hand, use pixels to order channels
            pid = self.getPixelsId()
            params = omero.sys.Parameters()
            params.map = {"pid": rlong(pid)}
            query = "select p from Pixels p join fetch p.channels as c join fetch c.logicalChannel as lc where p.id=:pid"
            pixels = self._conn.getQueryService().findByQuery(query, params)
            return [ChannelWrapper(self._conn, c, idx=n, re=self._re, img=self) for n,c in enumerate(pixels.iterateChannels())]

    def setActiveChannels(self, channels, windows=None, colors=None):
        """
        Sets the active channels on the rendering engine.
        Also sets rendering windows and channel colors (for channels that are active)
        
        @param channels:    List of active channel indexes ** 1-based index **
        @type channels:     List of int
        @param windows:     Start and stop values for active channel rendering settings
        @type windows:      List of tuples. [(20, 300), (None, None), (50, 500)]. Must be tuples for all channels
        @param colors:      List of colors. ['F00', None, '00FF00'].  Must be item for each channel
        """

        for c in range(len(self.getChannels())):
            self._re.setActive(c, (c+1) in channels)
            if (c+1) in channels:
                if windows is not None and windows[c][0] is not None and windows[c][1] is not None:
                    self._re.setChannelWindow(c, *windows[c])
                if colors is not None and colors[c]:
                    rgba = splitHTMLColor(colors[c])
                    if rgba:
                        self._re.setRGBA(c, *rgba)
        return True

    def getProjections (self):
        """
        Returns list of available keys for projection. E.g. ['intmax', 'intmean']
        
        @return:    Projection options
        @rtype:     List of strings
        """
        
        return self.PROJECTIONS.keys()

    def getProjection (self):
        """
        Returns the current projection option (checking it is valid).
        
        @return:    Projection key. E.g. 'intmax'
        @rtype:     String
        """
        
        if self._pr in self.PROJECTIONS.keys():
            return self._pr
        return 'normal'

    def setProjection (self, proj):
        """
        Sets the current projection option. 
        
        @param proj:    Projection Option. E.g. 'intmax' or 'normal'
        @type proj:     String
        """
        
        self._pr = proj

    def isInvertedAxis (self):
        """
        Returns the inverted axis flag
        
        @return:    Inverted Axis
        @rtype:     Boolean
        """
        
        return self._invertedAxis

    def setInvertedAxis (self, inverted):
        """
        Sets the inverted axis flag
        
        @param inverted:    Inverted Axis
        @type inverted:     Boolean
        """
        
        self._invertedAxis = inverted

    LINE_PLOT_DTYPES = {
        (4, True, True): 'f', # signed float
        (2, False, False): 'H', # unsigned short
        (2, False, True): 'h',  # signed short
        (1, False, False): 'B', # unsigned char
        (1, False, True): 'b',  # signed char
        }

    def getPixelLine (self, z, t, pos, axis, channels=None, range=None):
        """
        Grab a horizontal or vertical line from the image pixel data, for the specified channels
        (or 'active' if not specified) and using the specified range (or 1:1 relative to the image size).
        Axis may be 'h' or 'v', for horizontal or vertical respectively.
        
        @param z:           Z index
        @param t:           T index
        @param pos:         X or Y position
        @param axis:        Axis 'h' or 'v'
        @param channels:    map of {index: L{ChannelWrapper} }
        @param range:       height of scale (use image height (or width) by default)
        @return: rv         List of lists (one per channel)
        """
        
        if not self._loadPixels():
            logger.debug( "No pixels!")
            return None
        axis = axis.lower()[:1]
        if channels is None:
            channels = map(lambda x: x._idx, filter(lambda x: x.isActive(), self.getChannels()))
        if range is None:
            range = axis == 'h' and self.getSizeY() or self.getSizeX()
        if not isinstance(channels, (TupleType, ListType)):
            channels = (channels,)
        chw = map(lambda x: (x.getWindowMin(), x.getWindowMax()), self.getChannels())
        rv = []
        pixels_id = self._obj.getPrimaryPixels().getId().val
        rp = self._conn.createRawPixelsStore()
        rp.setPixelsId(pixels_id, True)
        for c in channels:
            bw = rp.getByteWidth()
            key = self.LINE_PLOT_DTYPES.get((bw, rp.isFloat(), rp.isSigned()), None)
            if key is None:
                logger.error("Unknown data type: " + str((bw, rp.isFloat(), rp.isSigned())))
            plot = array.array(key, axis == 'h' and rp.getRow(pos, z, c, t) or rp.getCol(pos, z, c, t))
            plot.byteswap() # TODO: Assuming ours is a little endian system
            # now move data into the windowMin..windowMax range
            offset = -chw[c][0]
            if offset != 0:
                plot = map(lambda x: x+offset, plot)
            normalize = 1.0/chw[c][1]*(range-1)
            if normalize != 1.0:
                plot = map(lambda x: x*normalize, plot)
            if isinstance(plot, array.array):
                plot = plot.tolist()
            rv.append(plot)
        return rv
        

    def getRow (self, z, t, y, channels=None, range=None):
        """
        Grab a horizontal line from the image pixel data, for the specified channels (or active ones)
        
        @param z:           Z index
        @param t:           T index
        @param y:           Y position of row
        @param channels:    map of {index: L{ChannelWrapper} }
        @param range:       height of scale (use image height by default)
        @return: rv         List of lists (one per channel)
        """
        
        return self.getPixelLine(z,t,y,'h',channels,range)

    def getCol (self, z, t, x, channels=None, range=None):
        """
        Grab a horizontal line from the image pixel data, for the specified channels (or active ones)
        
        @param z:           Z index
        @param t:           T index
        @param x:           X position of column
        @param channels:    map of {index: L{ChannelWrapper} }
        @param range:       height of scale (use image width by default)
        @return: rv         List of lists (one per channel)
        """
        
        return self.getPixelLine(z,t,x,'v',channels,range)

    @assert_re
    def getRenderingModels (self):
        """
        Gets a list of available rendering models.
        
        @return:    Rendering models
        @rtype:     List of L{BlitzObjectWrapper} 
        """
        
        if not len(self._rm):
            for m in [BlitzObjectWrapper(self._conn, m) for m in self._re.getAvailableModels()]:
                self._rm[m.value.lower()] = m
        return self._rm.values()

    @assert_re
    def getRenderingModel (self):
        """
        Get the current rendering model.
        
        @return:    Rendering model
        @rtype:     L{BlitzObjectWrapper}
        """
        
        return BlitzObjectWrapper(self._conn, self._re.getModel())

    def setGreyscaleRenderingModel (self):
        """
        Sets the Greyscale rendering model on this image's current renderer
        """
        
        rm = self.getRenderingModels()
        self._re.setModel(self._rm.get('greyscale', rm[0])._obj)

    def setColorRenderingModel (self):
        """
        Sets the HSB rendering model on this image's current renderer
        """
        
        rm = self.getRenderingModels()
        self._re.setModel(self._rm.get('rgb', rm[0])._obj)

    def isGreyscaleRenderingModel (self):
        """
        Returns True if the current rendering model is 'greyscale'
        
        @return:    isGreyscale
        @rtype:     Boolean
        """
        return self.getRenderingModel().value.lower() == 'greyscale'

    
    @assert_re
    def renderJpegRegion (self, z, t, x, y, width, height, level=None, compression=0.9):
        """
        Return the data from rendering a region of an image plane.
        NB. Projection not supported by the API currently. 
        
        @param z:               The Z index. Ignored if projecting image. 
        @param t:               The T index. 
        @param x:               The x coordinate of region (int)
        @param y:               The y coordinate of region (int)
        @param width:           The width of region (int)
        @param height:          The height of region (int)
        @param compression:     Compression level for jpeg
        @type compression:      Float
        """

        self._pd.z = long(z)
        self._pd.t = long(t)

        regionDef = omero.romio.RegionDef()
        regionDef.x = x
        regionDef.y = y
        regionDef.width = width
        regionDef.height = height
        self._pd.region = regionDef
        try:
            if level is not None:
                self._re.setResolutionLevel(level)
            if compression is not None:
                try:
                    self._re.setCompressionLevel(float(compression))
                except omero.SecurityViolation: #pragma: no cover
                    self._obj.clearPixels()
                    self._obj.pixelsLoaded = False
                    self._re = None
                    return self.renderJpeg(z,t,None)
            rv = self._re.renderCompressed(self._pd)
            return rv
        except omero.InternalException: #pragma: no cover
            logger.debug('On renderJpegRegion');
            logger.debug(traceback.format_exc())
            return None
        except Ice.MemoryLimitException: #pragma: no cover
            # Make sure renderCompressed isn't called again on this re, as it hangs
            self._obj.clearPixels()
            self._obj.pixelsLoaded = False
            self._re = None
            raise


    @assert_re
    def renderJpeg (self, z, t, compression=0.9):
        """
        Return the data from rendering image, compressed (and projected).
        Projection (or not) is specified by calling L{setProjection} before renderJpeg.
        
        @param z:               The Z index. Ignored if projecting image. 
        @param t:               The T index. 
        @param compression:     Compression level for jpeg
        @type compression:      Float
        """
        
        self._pd.z = long(z)
        self._pd.t = long(t)
        try:
            if compression is not None:
                try:
                    self._re.setCompressionLevel(float(compression))
                except omero.SecurityViolation: #pragma: no cover
                    self._obj.clearPixels()
                    self._obj.pixelsLoaded = False
                    self._re = None
                    return self.renderJpeg(z,t,None)
            projection = self.PROJECTIONS.get(self._pr, -1)
            if not isinstance(projection, omero.constants.projection.ProjectionType):
                rv = self._re.renderCompressed(self._pd)
            else:
                rv = self._re.renderProjectedCompressed(projection, self._pd.t, 1, 0, self.getSizeZ()-1)
            return rv
        except omero.InternalException: #pragma: no cover
            logger.debug('On renderJpeg');
            logger.debug(traceback.format_exc())
            return None
        except Ice.MemoryLimitException: #pragma: no cover
            # Make sure renderCompressed isn't called again on this re, as it hangs
            self._obj.clearPixels()
            self._obj.pixelsLoaded = False
            self._re = None
            raise

    def exportOmeTiff (self, bufsize=0):
        """
        Exports the OME-TIFF representation of this image.

        @type bufsize: int or tuple
        @param bufsize: if 0 return a single string buffer with the whole OME-TIFF
                        if >0 return a tuple holding total size and generator of chunks
                        (string buffers) of bufsize bytes each
        @return:        OME-TIFF file data
        @rtype:         String or (size, data generator)
        """
        
        e = self._conn.createExporter()
        e.addImage(self.getId())
        size = e.generateTiff()
        if bufsize==0:
            # Read it all in one go
            return fileread(e, size, 65536)
        else:
            # generator using bufsize
            return (size, fileread_gen(e, size, bufsize))

    def _wordwrap (self, width, text, font):
        """
        Wraps text into lines that are less than a certain width (when rendered 
        in specified font)
        
        @param width:   The max width to wrap text (pixels)
        @type width:    Int
        @param text:    The text to wrap 
        @type text:     String
        @param font:    Font to use. 
        @type font:     E.g. PIL ImageFont
        @return:        List of text lines
        @rtype:         List of Strings
        """
        
        rv = []
        tokens = filter(None, text.split(' '))
        while len(tokens) > 1:
            p1 = 0
            p2 = 1
            while p2 <= len(tokens) and font.getsize(' '.join(tokens[p1:p2]))[0] < width:
                p2 += 1
            rv.append(' '.join(tokens[p1:p2-1]))
            tokens = tokens[p2-1:]
        if len(tokens):
            rv.append(' '.join(tokens))
        logger.debug(rv)
        return rv

    @assert_re
    def createMovie (self, outpath, zstart, zend, tstart, tend, opts=None):
        """
        Creates a movie file from this image.
        TODO:   makemovie import is commented out in 4.2+

        @type outpath: string
        @type zstart: int
        @type zend: int
        @type tstart: int
        @type tend: int
        @type opts: dict
        @param opts: dictionary of extra options. Currently processed options are:
                     - watermark:string: path to image to use as watermark
                     - slides:tuple: tuple of tuples with slides to prefix video with
                       in format (secs:int, topline:text[, middleline:text[, bottomline:text]])
                     - fps:int: frames per second
                     - minsize: tuple of (minwidth, minheight, bgcolor)
                    - format:string: one of video/mpeg or video/quicktime
                    
        @return:    Tuple of (file-ext, format)
        @rtype:     (String, String)
        """
        logger.warning('createMovie support is currently disabled.')
        logger.warning('  - see https://trac.openmicroscopy.org.uk/ome/ticket/3857')
        return None, None
        if opts is None: opts = {}
        slides = opts.get('slides', None)
        minsize = opts.get('minsize', None)
        w, h = self.getSizeX(), self.getSizeY()
        watermark = opts.get('watermark', None)
        if watermark:
            watermark = Image.open(watermark)
            if minsize is not None:
                ratio = min(float(w) / minsize[0], float(h) / minsize[1])
                if ratio > 1:
                    watermark = watermark.resize(map(lambda x: x*ratio, watermark.size), Image.ANTIALIAS)
            ww, wh = watermark.size
        else:
            ww, wh = 0, 0
        if minsize is not None and (w < minsize[0] or h < minsize[1]):
            w = max(w, minsize[0])
            h = max(h, minsize[1])
        else:
            minsize = None
        wmpos = 0, h - wh
        fps = opts.get('fps', 4)
        def recb (*args):
            return self._re
        fsizes = (8,8,12,18,24,32,32,40,48,56,56,64)
        fsize = fsizes[max(min(int(w / 256)-1, len(fsizes)), 1) - 1]
        scalebars = (1,1,2,2,5,5,5,5,10,10,10,10)
        scalebar = scalebars[max(min(int(w / 256)-1, len(scalebars)), 1) - 1]
        font = ImageFont.load('%s/pilfonts/B%0.2d.pil' % (THISPATH, fsize) )
        def introcb (pixels, commandArgs):
            for t in slides:
                slide = Image.new("RGBA", (w,h))
                for i, line in enumerate(t[1:4]):
                    line = line.decode('utf8').encode('iso8859-1')
                    wwline = self._wordwrap(w, line, font)
                    for j, line in enumerate(wwline):
                        tsize = font.getsize(line)
                        draw = ImageDraw.Draw(slide)
                        if i == 0:
                            y = 10+j*tsize[1]
                        elif i == 1:
                            y = h / 2 - ((len(wwline)-j)*tsize[1]) + (len(wwline)*tsize[1])/2
                        else:
                            y = h - (len(wwline) - j)*tsize[1] - 10
                        draw.text((w/2-tsize[0]/2,y), line, font=font)
                for i in range(t[0]*fps):
                    yield slide
        if minsize is not None:
            bg = Image.new("RGBA", (w, h), minsize[2])
            ovlpos = (w-self.getSizeX()) / 2, (h-self.getSizeY()) / 2
            def resize (image):
                img = bg.copy()
                img.paste(image, ovlpos, image)
                return img
        else:
            def resize (image):
                return image
        def imgcb (z, t, pixels, image, commandArgs, frameNo):
            image = resize(image)
            if watermark:
                image.paste(watermark, wmpos, watermark)
            return image
        d = tempfile.mkdtemp()
        orig = os.getcwd()
        os.chdir(d)
        ca = makemovie.buildCommandArgs(self.getId(), scalebar=scalebar)
        ca['imageCB'] = imgcb
        if slides:
            ca['introCB'] = introcb
        ca['fps'] = fps
        ca['format'] = opts.get('format', 'video/quicktime')
        ca['zStart'] = int(zstart)
        ca['zEnd'] = int(zend)
        ca['tStart'] = int(tstart)
        ca['tEnd'] = int(tend)
        ca['font'] = font
        logger.debug(ca)
        try:
            fn = os.path.abspath(makemovie.buildMovie(ca, self._conn.c.getSession(), self, self.getPrimaryPixels()._obj, recb))
        except:
            logger.error(traceback.format_exc())
            raise
        os.chdir(orig)
        shutil.move(fn, outpath)
        shutil.rmtree(d)
        return os.path.splitext(fn)[-1], ca['format']

    def renderImage (self, z, t, compression=0.9):
        """
        Render the Image, (projected) and compressed. 
        For projection, call L{setProjection} before renderImage. 
        
        @param z:       Z index
        @param t:       T index
        @compression:   Image compression level 
        @return:        A PIL Image or None
        @rtype:         PIL Image. 
        """
        
        rv = self.renderJpeg(z,t,compression)
        if rv is not None:
            i = StringIO(rv)
            rv = Image.open(i)
        return rv

    def renderSplitChannel (self, z, t, compression=0.9, border=2):
        """
        Prepares a jpeg representation of a 2d grid holding a render of each channel, 
        along with one for all channels at the set Z and T points.
        
        @param z:       Z index
        @param t:       T index
        @param compression: Image compression level 
        @param border:
        @return: value
        """
        
        img = self.renderSplitChannelImage(z,t,compression, border)
        rv = StringIO()
        img.save(rv, 'jpeg', quality=int(compression*100))
        return rv.getvalue()

    def splitChannelDims (self, border=2):
        """
        Returns a dict of layout parameters for generating split channel image.
        E.g. row count, column count etc.  for greyscale and color layouts. 
        
        @param border:  spacing between panels
        @type border:   int
        @return:        Dict of parameters
        @rtype:         Dict
        """
        
        c = self.getSizeC()
        # Greyscale, no channel overlayed image
        x = sqrt(c)
        y = int(round(x))
        if x > y:
            x = y+1
        else:
            x = y
        rv = {'g':{'width': self.getSizeX()*x + border*(x+1),
              'height': self.getSizeY()*y+border*(y+1),
              'border': border,
              'gridx': x,
              'gridy': y,}
              }
        # Color, one extra image with all channels overlayed
        c += 1
        x = sqrt(c)
        y = int(round(x))
        if x > y:
            x = y+1
        else:
            x = y
        rv['c'] = {'width': self.getSizeX()*x + border*(x+1),
              'height': self.getSizeY()*y+border*(y+1),
              'border': border,
              'gridx': x,
              'gridy': y,}
        return rv

    def renderSplitChannelImage (self, z, t, compression=0.9, border=2):
        """
        Prepares a PIL Image with a 2d grid holding a render of each channel, 
        along with one for all channels at the set Z and T points.
        
        @param z:   Z index
        @param t:   T index
        @param compression: Compression level
        @param border:  space around each panel (int)
        @return:        canvas
        @rtype:         PIL Image
        """
                
        dims = self.splitChannelDims(border=border)[self.isGreyscaleRenderingModel() and 'g' or 'c']
        canvas = Image.new('RGBA', (dims['width'], dims['height']), '#fff')
        cmap = [ch.isActive() and i+1 or 0 for i,ch in enumerate(self.getChannels())]
        c = self.getSizeC()
        pxc = 0
        px = dims['border']
        py = dims['border']
        
        # Font sizes depends on image width
        w = self.getSizeX()
        if w >= 640:
            fsize = (int((w-640)/128)*8) + 24
            if fsize > 64:
                fsize = 64
        elif w >= 512:
            fsize = 24
        elif w >= 384: #pragma: no cover
            fsize = 18
        elif w >= 298: #pragma: no cover
            fsize = 14
        elif w >= 256: #pragma: no cover
            fsize = 12
        elif w >= 213: #pragma: no cover
            fsize = 10
        elif w >= 96: #pragma: no cover
            fsize = 8
        else: #pragma: no cover
            fsize = 0
        if fsize > 0:
            font = ImageFont.load('%s/pilfonts/B%0.2d.pil' % (THISPATH, fsize) )


        for i in range(c):
            if cmap[i]:
                self.setActiveChannels((i+1,))
                img = self.renderImage(z,t, compression)
                if fsize > 0:
                    draw = ImageDraw.ImageDraw(img)
                    draw.text((2,2), "%s" % (str(self.getChannels()[i].getLabel())), font=font, fill="#fff")
                canvas.paste(img, (px, py))
            pxc += 1
            if pxc < dims['gridx']:
                px += self.getSizeX() + border
            else:
                pxc = 0
                px = border
                py += self.getSizeY() + border
        if not self.isGreyscaleRenderingModel():
            self.setActiveChannels(cmap)
            img = self.renderImage(z,t, compression)
            if fsize > 0:
                draw = ImageDraw.ImageDraw(img)
                draw.text((2,2), "merged", font=font, fill="#fff")
            canvas.paste(img, (px, py))
        return canvas

    LP_PALLETE = [0,0,0,0,0,0,255,255,255]
    LP_TRANSPARENT = 0 # Some color
    LP_BGCOLOR = 1 # Black
    LP_FGCOLOR = 2 # white
    def prepareLinePlotCanvas (self):
        """
        Common part of horizontal and vertical line plot rendering.
        
        @returns: (Image, width, height).
        """
        channels = filter(lambda x: x.isActive(), self.getChannels())
        width = self.getSizeX()
        height = self.getSizeY()

        pal = list(self.LP_PALLETE)
        # Prepare the palette taking channel colors in consideration
        for channel in channels:
            pal.extend(channel.getColor().getRGB())

        # Prepare the PIL classes we'll be using
        im = Image.new('P', (width, height))
        im.putpalette(pal)
        return im, width, height


    @assert_re
    def renderRowLinePlotGif (self, z, t, y, linewidth=1):
        """
        Draws the Row plot as a gif file. Returns gif data.  
        
        @param z:   Z index
        @param t:   T index
        @param y:   Y position
        @param linewidth:   Width of plot line
        @return:    gif data as String
        @rtype:     String
        """
        
        self._pd.z = long(z)
        self._pd.t = long(t)

        im, width, height = self.prepareLinePlotCanvas()
        base = height - 1

        draw = ImageDraw.ImageDraw(im)
        # On your marks, get set... go!
        draw.rectangle([0, 0, width-1, base], fill=self.LP_TRANSPARENT, outline=self.LP_TRANSPARENT)
        draw.line(((0,y),(width, y)), fill=self.LP_FGCOLOR, width=linewidth)

        # Grab row data
        rows = self.getRow(z,t,y)

        for r in range(len(rows)):
            chrow = rows[r]
            color = r + self.LP_FGCOLOR + 1
            last_point = base-chrow[0]
            for i in range(len(chrow)):
                draw.line(((i, last_point), (i, base-chrow[i])), fill=color, width=linewidth)
                last_point = base-chrow[i]
        del draw
        out = StringIO()
        im.save(out, format="gif", transparency=0)
        return out.getvalue()

    @assert_re
    def renderColLinePlotGif (self, z, t, x, linewidth=1):
        """
        Draws the Column plot as a gif file. Returns gif data.  
        
        @param z:   Z index
        @param t:   T index
        @param x:   X position
        @param linewidth:   Width of plot line
        @return:    gif data as String
        @rtype:     String
        """
        
        self._pd.z = long(z)
        self._pd.t = long(t)

        im, width, height = self.prepareLinePlotCanvas()

        draw = ImageDraw.ImageDraw(im)
        # On your marks, get set... go!
        draw.rectangle([0, 0, width-1, height-1], fill=self.LP_TRANSPARENT, outline=self.LP_TRANSPARENT)
        draw.line(((x,0),(x, height)), fill=self.LP_FGCOLOR, width=linewidth)

        # Grab col data
        cols = self.getCol(z,t,x)

        for r in range(len(cols)):
            chcol = cols[r]
            color = r + self.LP_FGCOLOR + 1
            last_point = chcol[0]
            for i in range(len(chcol)):
                draw.line(((last_point, i), (chcol[i], i)), fill=color, width=linewidth)
                last_point = chcol[i]
        del draw
        out = StringIO()
        im.save(out, format="gif", transparency=0)
        return out.getvalue()

    @assert_re
    def getZ (self):
        """
        Returns the last used value of Z (E.g. for renderingJpeg or line plot)
        Returns 0 if these methods not been used yet.
        TODO: How to get default-Z?
        
        @return:    current Z index
        @rtype:     int
        """
        
        return self._pd.z

    @assert_re
    def getT (self):
        """
        Returns the last used value of T (E.g. for renderingJpeg or line plot)
        Returns 0 if these methods not been used yet. 
        TODO: How to get default-T?
        
        @return:    current T index
        @rtype:     int
        """
        
        return self._pd.t

    @assert_re
    def getDefaultZ(self):
        """
        Gets the default Z index from the rendering engine
        """
        return self._re.getDefaultZ()

    @assert_re
    def getDefaultT(self):
        """
        Gets the default T index from the rendering engine
        """
        return self._re.getDefaultT()

    @assert_pixels
    def getPixelsType (self):
        """
        Gets the physical size X of pixels in microns
        
        @return:    Size of pixel in x or O
        @rtype:     float
        """
        rv = self._obj.getPrimaryPixels().getPixelsType().value
        return rv is not None and rv.val or 'unknown'
    
    @assert_pixels
    def getPixelSizeX (self):
        """
        Gets the physical size X of pixels in microns
        
        @return:    Size of pixel in x or O
        @rtype:     float
        """
        rv = self._obj.getPrimaryPixels().getPhysicalSizeX()
        return rv is not None and rv.val or 0

    @assert_pixels
    def getPixelSizeY (self):
        """
        Gets the physical size Y of pixels in microns
        
        @return:    Size of pixel in y or O
        @rtype:     float
        """
        
        rv = self._obj.getPrimaryPixels().getPhysicalSizeY()
        return rv is not None and rv.val or 0

    @assert_pixels
    def getPixelSizeZ (self):
        """
        Gets the physical size Z of pixels in microns
        
        @return:    Size of pixel in z or O
        @rtype:     float
        """
        
        rv = self._obj.getPrimaryPixels().getPhysicalSizeZ()
        return rv is not None and rv.val or 0

    @assert_pixels
    def getSizeX (self):
        """
        Gets width (size X) of the image (in pixels)
        
        @return:    width
        @rtype:     int
        """
        
        return self._obj.getPrimaryPixels().getSizeX().val

    @assert_pixels
    def getSizeY (self):
        """
        Gets height (size Y) of the image (in pixels)
        
        @return:    height
        @rtype:     int
        """
        
        return self._obj.getPrimaryPixels().getSizeY().val

    @assert_pixels
    def getSizeZ (self):
        """
        Gets Z count of the image
        
        @return:    size Z
        @rtype:     int
        """
        
        if self.isInvertedAxis():
            return self._obj.getPrimaryPixels().getSizeT().val
        else:
            return self._obj.getPrimaryPixels().getSizeZ().val

    @assert_pixels
    def getSizeT (self):
        """
        Gets T count of the image
        
        @return:    size T
        @rtype:     int
        """
        
        if self.isInvertedAxis():
            return self._obj.getPrimaryPixels().getSizeZ().val
        else:
            return self._obj.getPrimaryPixels().getSizeT().val

    @assert_pixels
    def getSizeC (self):
        """
        Gets C count of the image (number of channels)
        
        @return:    size C
        @rtype:     int
        """
        
        return self._obj.getPrimaryPixels().getSizeC().val

    def clearDefaults (self):
        """
        Removes specific color settings from channels
        
        @return:    True if allowed to do this
        @rtype:     Boolean
        """
        
        if not self.canWrite():
            return False
        for c in self.getChannels():
            c.unloadRed()
            c.unloadGreen()
            c.unloadBlue()
            c.unloadAlpha()
            c.save()
        self._conn.getDeleteService().deleteSettings(self.getId())
        return True

    def _collectRenderOptions (self):
        """
        Returns a map of rendering options not stored in rendering settings. 
            - 'p' : projection
            - 'ia' : inverted axis (swap Z and T)
        
        @return:    Dict of render options
        @rtype:     Dict
        """
        
        rv = {}
        rv['p'] = self.getProjection()
        rv['ia'] = self.isInvertedAxis() and "1" or "0"
        return rv

    def _loadRenderOptions (self):
        """
        Loads rendering options from an Annotation on the Image.
        
        @return:    Dict of rendering options
        @rtype:     Dict 
        """
        ns = self._conn.CONFIG.get('IMG_ROPTSNS', None)
        if ns:
            ann = self.getAnnotation(ns)
            if ann is not None:
                opts = dict([x.split('=') for x in ann.getValue().split('&')])
                return opts
        return {}

    def loadRenderOptions (self):
        """
        Loads rendering options from an Annotation on the Image and applies them
        to the Image. 
        
        @return:    True!    TODO: Always True??
        """
        opts = self._loadRenderOptions()
        self.setProjection(opts.get('p', None))
        self.setInvertedAxis(opts.get('ia', "0") == "1")
        return True

    @assert_re
    def saveDefaults (self):
        """
        Limited support for saving the current prepared image rendering defs.
        Right now only channel colors are saved back.
        
        @return: Boolean
        """
        
        if not self.canWrite():
            return False
        ns = self._conn.CONFIG.get('IMG_ROPTSNS', None)
        if ns:
            opts = self._collectRenderOptions()
            self.removeAnnotations(ns)
            ann = omero.gateway.CommentAnnotationWrapper()
            ann.setNs(ns)
            ann.setValue('&'.join(['='.join(map(str, x)) for x in opts.items()]))
            self.linkAnnotation(ann)
        self._re.saveCurrentSettings()
        return True

ImageWrapper = _ImageWrapper

## INSTRUMENT AND ACQUISITION ##

class _ImageStageLabelWrapper (BlitzObjectWrapper):
    """
    omero_model_StageLabelI class wrapper extends BlitzObjectWrapper.
    """
    pass

ImageStageLabelWrapper = _ImageStageLabelWrapper

class _ImagingEnvironmentWrapper(BlitzObjectWrapper):
    """
    omero_model_ImagingEnvironment class wrapper extends BlitzObjectWrapper.
    """
    pass

ImagingEnvironmentWrapper = _ImagingEnvironmentWrapper

class _ImagingEnviromentWrapper (BlitzObjectWrapper):
    """
    omero_model_ImagingEnvironmentI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('temperature',
              'airPressure',
              'humidity',
              'co2percent',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'ImagingEnvironment'
    
ImagingEnviromentWrapper = _ImagingEnviromentWrapper

class _TransmittanceRangeWrapper (BlitzObjectWrapper):
    """
    omero_model_TransmittanceRangeI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('cutIn',
              'cutOut',
              'cutInTolerance',
              'cutOutTolerance',
              'transmittance',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'TransmittanceRange'

TransmittanceRangeWrapper = _TransmittanceRangeWrapper

class _DetectorSettingsWrapper (BlitzObjectWrapper):
    """
    omero_model_DetectorSettingsI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('voltage',
              'gain',
              'offsetValue',
              'readOutRate',
              'binning|BinningWrapper',
              'detector|DetectorWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'DetectorSettings'

DetectorSettingsWrapper = _DetectorSettingsWrapper

class _BinningWrapper (BlitzObjectWrapper):
    """
    omero_model_BinningI class wrapper extends BlitzObjectWrapper.
    """

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Binning'

BinningWrapper = _BinningWrapper

class _DetectorWrapper (BlitzObjectWrapper):
    """
    omero_model_DetectorI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'serialNumber',
              'voltage',
              'gain',
              'offsetValue',
              'zoom',
              'amplificationGain',
              '#type;detectorType',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Detector'

    def getDetectorType(self):
        """
        The type of detector (enum value)
        
        @return:    Detector type
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv

DetectorWrapper = _DetectorWrapper

class _ObjectiveWrapper (BlitzObjectWrapper):
    """
    omero_model_ObjectiveI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'serialNumber',
              'nominalMagnification',
              'calibratedMagnification',
              'lensNA',
              '#immersion',
              '#correction',
              'workingDistance',
              '#iris',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Objective'

    def getImmersion(self):
        """
        The type of immersion for this objective (enum value)
        
        @return:    Immersion type, or None
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.immersion
        if self.immersion is not None:
            rv = EnumerationWrapper(self._conn, self.immersion)
            if not self.immersion.loaded:
                self.immersion = rv._obj
            return rv
    
    def getCorrection(self):
        """
        The type of Correction for this objective (enum value)
        
        @return:    Correction type, or None
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.correction
        if self.correction is not None:
            rv = EnumerationWrapper(self._conn, self.correction)
            if not self.correction.loaded:
                self.correction = rv._obj
            return rv

    def getIris(self):
        """
        The type of Iris for this objective (enum value)
        
        @return:    Iris type
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.iris
        if self.iris is not None:
            rv = EnumerationWrapper(self._conn, self.iris)
            if not self.iris.loaded:
                self.iris = rv._obj
            return rv

ObjectiveWrapper = _ObjectiveWrapper

class _ObjectiveSettingsWrapper (BlitzObjectWrapper):
    """
    omero_model_ObjectiveSettingsI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('correctionCollar',
              '#medium',
              'refractiveIndex',
              'objective|ObjectiveWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'ObjectiveSettings'

    def getObjective (self):
        """
        Gets the Objective that these settings refer to 
        
        @return:    Objective
        @rtype:     L{ObjectiveWrapper}
        """
        
        rv = self.objective
        if self.objective is not None:
            rv = ObjectiveWrapper(self._conn, self.objective)
            if not self.objective.loaded:
                self.objective = rv._obj
        return rv

    def getMedium(self):
        """
        Gets the Medium type that these settings refer to (enum value)
        
        @return:    Medium
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.medium
        if self.medium is not None:
            rv = EnumerationWrapper(self._conn, self.medium)
            if not self.medium.loaded:
                self.medium = rv._obj
            return rv

ObjectiveSettingsWrapper = _ObjectiveSettingsWrapper


class _FilterWrapper (BlitzObjectWrapper):
    """
    omero_model_FilterI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'lotNumber',
              'filterWheel',
              '#type;filterType',
              'transmittanceRange|TransmittanceRangeWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Filter'
    
    def getFilterType(self):
        """
        Gets the Filter type for this filter (enum value)
        
        @return:    Filter type
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv

FilterWrapper = _FilterWrapper

class _DichroicWrapper (BlitzObjectWrapper):
    """
    omero_model_DichroicI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'lotNumber',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Dichroic'

DichroicWrapper = _DichroicWrapper

class _FilterSetWrapper (BlitzObjectWrapper):
    """
    omero_model_FilterSetI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'lotNumber',
              'dichroic|DichroicWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'FilterSet'
    
    def copyEmissionFilters(self):
        """ TODO: not implemented """
        pass

    def copyExcitationFilters(self):
        """ TODO: not implemented """
        pass
    
FilterSetWrapper = _FilterSetWrapper

class _OTFWrapper (BlitzObjectWrapper):
    """
    omero_model_OTFI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('sizeX',
              'sizeY',
              'opticalAxisAveraged'
              'pixelsType',
              'path',
              'filterSet|FilterSetWrapper',
              'objective|ObjectiveWrapper',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'OTF'

OTFWrapper = _OTFWrapper

class _LightSettingsWrapper (BlitzObjectWrapper):
    """
    base Light Source class wrapper, extends BlitzObjectWrapper.
    """
    _attrs = ('attenuation',
              'wavelength',
              #'lightSource|LightSourceWrapper',
              'microbeamManipulation',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'LightSettings'

    def getLightSource(self):
        if self._obj.lightSource is None:
            return None
        if not self._obj.lightSource.isLoaded():    # see #5742
            lid = self._obj.lightSource.id.val
            params = omero.sys.Parameters()
            params.map = {"id": rlong(lid)}
            query = "select l from Laser as l left outer join fetch l.type " \
                    "left outer join fetch l.laserMedium " \
                    "left outer join fetch l.pulse as pulse " \
                    "left outer join fetch l.pump as pump " \
                    "left outer join fetch pump.type as pt " \
                    "where l.id = :id"
            self._obj.lightSource = self._conn.getQueryService().findByQuery(query, params)
        return LightSourceWrapper(self._conn, self._obj.lightSource)

LightSettingsWrapper = _LightSettingsWrapper

class _LightSourceWrapper (BlitzObjectWrapper):
    """
    base Light Source class wrapper, extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'power',
              'serialNumber',
              '#type;lightSourceType',
              'version')

    def getLightSourceType(self):
        """
        Gets the Light Source type for this light source (enum value)
        
        @return:    Light Source type
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv

# map of light source gateway classes to omero model objects. E.g. omero.model.Arc : 'ArcWrapper'
_LightSourceClasses = {}
def LightSourceWrapper (conn, obj, **kwargs):
    """
    Creates wrapper instances for omero.model light source objects
    
    @param conn:    L{BlitzGateway} connection
    @param obj:     omero.model object
    @return:        L{_LightSourceWrapper} subclass
    """
    for k, v in _LightSourceClasses.items():
        if isinstance(obj, k):
            return getattr(omero.gateway, v)(conn, obj, **kwargs)
    return None

class _FilamentWrapper (_LightSourceWrapper):
    """
    omero_model_FilamentI class wrapper extends LightSourceWrapper.
    """

    def __bstrap__ (self):
        super(_FilamentWrapper, self).__bstrap__()
        self.OMERO_CLASS = 'Filament'

FilamentWrapper = _FilamentWrapper
_LightSourceClasses[omero.model.FilamentI] = 'FilamentWrapper'

class _ArcWrapper (_FilamentWrapper):
    """
    omero_model_ArcI class wrapper extends FilamentWrapper.
    """
    def __bstrap__ (self):
        super(_ArcWrapper, self).__bstrap__()
        self.OMERO_CLASS = 'Arc'

ArcWrapper = _ArcWrapper
_LightSourceClasses[omero.model.ArcI] = 'ArcWrapper'

class _LaserWrapper (_LightSourceWrapper):
    """
    omero_model_LaserI class wrapper extends LightSourceWrapper.
    """
    def __bstrap__ (self):
        super(_LaserWrapper, self).__bstrap__()
        self.OMERO_CLASS = 'Laser'
        self._attrs += (
            '#laserMedium',
            'frequencyMultiplication',
            'tuneable',
            'pulse',
            'wavelength',
            'pockelCell',
            'pump',
            'repetitionRate')

    def getLaserMedium(self):
        """
        Gets the laser medium type for this Laser (enum value)
        
        @return:    Laser medium type
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.laserMedium
        if self.laserMedium is not None:
            rv = EnumerationWrapper(self._conn, self.laserMedium)
            if not self.laserMedium.loaded:
                self.laserMedium = rv._obj
            return rv

LaserWrapper = _LaserWrapper
_LightSourceClasses[omero.model.LaserI] = 'LaserWrapper'

class _LightEmittingDiodeWrapper (_LightSourceWrapper):
    """
    omero_model_LightEmittingDiodeI class wrapper extends LightSourceWrapper.
    """
    def __bstrap__ (self):
        super(_LightEmittingDiodeWrapper, self).__bstrap__()
        self.OMERO_CLASS = 'LightEmittingDiode'

LightEmittingDiodeWrapper = _LightEmittingDiodeWrapper
_LightSourceClasses[omero.model.LightEmittingDiodeI] = 'LightEmittingDiodeWrapper'

class _MicroscopeWrapper (BlitzObjectWrapper):
    """
    omero_model_MicroscopeI class wrapper extends BlitzObjectWrapper.
    """
    _attrs = ('manufacturer',
              'model',
              'serialNumber',
              '#type;microscopeType',
              'version')

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Microscope'

    def getMicroscopeType(self):
        """
        Returns the 'type' of microscope this is. 
        
        @return:    Microscope type.
        @rtype:     L{EnumerationWrapper}
        """
        
        rv = self.type
        if self.type is not None:
            rv = EnumerationWrapper(self._conn, self.type)
            if not self.type.loaded:
                self.type = rv._obj
            return rv

MicroscopeWrapper = _MicroscopeWrapper

class _InstrumentWrapper (BlitzObjectWrapper):
    """
    omero_model_InstrumentI class wrapper extends BlitzObjectWrapper.
    """

    # TODO: wrap version

    _attrs = ('microscope|MicroscopeWrapper',)

    def __bstrap__ (self):
        self.OMERO_CLASS = 'Instrument'

    def getMicroscope (self):
        """
        Returns the microscope component of the Instrument. 
        
        @return:    Microscope
        @rtype:     omero.model.Microscope
        """
        
        if self._obj.microscope is not None:
            return MicroscopeWrapper(self._conn, self._obj.microscope)
        return None
           
    def getDetectors (self):
        """
        Gets the Instrument detectors. 
        
        @return:    List of Detectors
        @rtype:     L{DetectorWrapper} list
        """
        
        return [DetectorWrapper(self._conn, x) for x in self._detectorSeq]

    def getObjectives (self):
        """
        Gets the Instrument Objectives. 
        
        @return:    List of Objectives
        @rtype:     L{ObjectiveWrapper} list
        """
        
        return [ObjectiveWrapper(self._conn, x) for x in self._objectiveSeq]

    def getFilters (self):
        """
        Gets the Instrument Filters. 
        
        @return:    List of Filters
        @rtype:     L{FilterWrapper} list
        """
        
        return [FilterWrapper(self._conn, x) for x in self._filterSeq]

    def getDichroics (self):
        """
        Gets the Instrument Dichroics. 
        
        @return:    List of Dichroics
        @rtype:     L{DichroicWrapper} list
        """
        
        return [DichroicWrapper(self._conn, x) for x in self._dichroicSeq]

    def getFilterSets (self):
        """
        Gets the Instrument FilterSets. 
        
        @return:    List of FilterSets
        @rtype:     L{FilterSetWrapper} list
        """
        
        return [FilterSetWrapper(self._conn, x) for x in self._filterSetSeq]

    def getOTFs (self):
        """
        Gets the Instrument OTFs. 
        
        @return:    List of OTFs
        @rtype:     L{OTFWrapper} list
        """
        
        return [OTFWrapper(self._conn, x) for x in self._otfSeq]

    def getLightSources (self):
        """
        Gets the Instrument LightSources. 
        
        @return:    List of LightSources
        @rtype:     L{LightSourceWrapper} list
        """
        
        return [LightSourceWrapper(self._conn, x) for x in self._lightSourceSeq]


    def simpleMarshal (self):
        if self._obj:
            rv = super(_InstrumentWrapper, self).simpleMarshal(parents=False)
            rv['detectors'] = [x.simpleMarshal() for x in self.getDetectors()]
            rv['objectives'] = [x.simpleMarshal() for x in self.getObjectives()]
            rv['filters'] = [x.simpleMarshal() for x in self.getFilters()]
            rv['dichroics'] = [x.simpleMarshal() for x in self.getDichroics()]
            rv['filterSets'] = [x.simpleMarshal() for x in self.getFilterSets()]
            rv['otfs'] = [x.simpleMarshal() for x in self.getOTFs()]
            rv['lightsources'] = [x.simpleMarshal() for x in self.getLightSources()]
        else:
            rv = {}
        return rv

InstrumentWrapper = _InstrumentWrapper

KNOWN_WRAPPERS = {}


def refreshWrappers ():
    """
    this needs to be called by modules that extend the base wrappers
    """
    KNOWN_WRAPPERS.update({"project":ProjectWrapper,
                  "dataset":DatasetWrapper,
                  "image":ImageWrapper,
                  "screen":ScreenWrapper,
                  "plate":PlateWrapper,
                  "well":WellWrapper,
                  "experimenter":ExperimenterWrapper,
                  "experimentergroup":ExperimenterGroupWrapper,
                  "originalfile":OriginalFileWrapper,
                  "commentannotation":CommentAnnotationWrapper,
                  "tagannotation":TagAnnotationWrapper,
                  "longannotation":LongAnnotationWrapper,
                  "booleanannotation":BooleanAnnotationWrapper,
                  "fileannotation":FileAnnotationWrapper,
                  "doubleannotation":DoubleAnnotationWrapper,
                  "termannotation":TermAnnotationWrapper,
                  "timestampannotation":TimestampAnnotationWrapper,
                  "annotation":AnnotationWrapper._wrap})    # allows for getObjects("Annotation", ids)

refreshWrappers()
