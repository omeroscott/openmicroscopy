/*
 * org.openmicroscopy.shoola.agents.treeviewer.RefreshExperimenterDataLoader 
 *
 *------------------------------------------------------------------------------
 *  Copyright (C) 2006-2007 University of Dundee. All rights reserved.
 *
 *
 * 	This program is free software; you can redistribute it and/or modify
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
 */
package org.openmicroscopy.shoola.agents.treeviewer;


//Java imports
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.Map.Entry;

//Third-party libraries

//Application-internal dependencies
import org.openmicroscopy.shoola.agents.treeviewer.browser.Browser;
import org.openmicroscopy.shoola.agents.util.browser.TreeFileSet;
import org.openmicroscopy.shoola.agents.util.browser.TreeImageDisplay;
import org.openmicroscopy.shoola.agents.util.browser.TreeImageSet;
import org.openmicroscopy.shoola.agents.util.browser.TreeImageTimeSet;
import org.openmicroscopy.shoola.env.data.model.TimeRefObject;
import org.openmicroscopy.shoola.env.data.views.CallHandle;
import pojos.DataObject;
import pojos.DatasetData;
import pojos.FileAnnotationData;
import pojos.GroupData;
import pojos.ImageData;
import pojos.ProjectData;
import pojos.ScreenData;
import pojos.TagAnnotationData;

/** 
 * Reloads the data for the specified experimenters.
 * This class calls the <code>refreshHierarchy</code> in the
 * <code>DataManagerView</code>.
 *
 * @author  Jean-Marie Burel &nbsp;&nbsp;&nbsp;&nbsp;
 * <a href="mailto:j.burel@dundee.ac.uk">j.burel@dundee.ac.uk</a>
 * @author Donald MacDonald &nbsp;&nbsp;&nbsp;&nbsp;
 * <a href="mailto:donald@lifesci.dundee.ac.uk">donald@lifesci.dundee.ac.uk</a>
 * @version 3.0
 * <small>
 * (<b>Internal version:</b> $Revision: $Date: $)
 * </small>
 * @since OME3.0
 */
public class RefreshExperimenterDataLoader
	extends DataBrowserLoader
{
	
	/** The type of the nodes to select when done. */
    private Class								type;
    
    /** The identifier of the object to select when done. */
    private long								id;
    
    /** The type of the root node. */
    private Class								rootNodeType;
    
    /** Collection of {@link RefreshExperimenterDef} objects. */
    private Map<Long, RefreshExperimenterDef>	expNodes;
    
    /** Handle to the asynchronous call so that we can cancel it. */
    private CallHandle  						handle;
    
    /** The node of reference hosting the node to browse. */
    private Object 								refNode;
    
    /** The data object to browse. */
    private DataObject 							toBrowse;
    
    /**
     * Controls if the passed class is supported.
     * 
     * @param klass The class to check.
     */
    private void checkClass(Class klass)
    {
        if (ProjectData.class.equals(klass) || ImageData.class.equals(klass) ||
        	TagAnnotationData.class.equals(klass) || 
        	DatasetData.class.equals(klass) || 
        	FileAnnotationData.class.equals(klass) ||
        	ScreenData.class.equals(klass) || GroupData.class.equals(klass))
            return;
        throw new IllegalArgumentException("Root node not supported.");
    }
    
    /**
     * Formats the results.
     * 
     * @param expId		The user's id.
     * @param result	The result of the call for the passed user.
     */
    private void setExperimenterResult(long expId, Object result)
    {
    	RefreshExperimenterDef node = expNodes.get(expId);
    	Map<DataObject, Set> map;
    	Map expandedNodes = node.getExpandedTopNodes();
        if (expandedNodes == null || expandedNodes.size() == 0 
        	|| result instanceof Collection) {
        	Collection set = (Collection) result;
            Iterator j = set.iterator();
            map = new HashMap<DataObject, Set>();
            DataObject parent;
            Set children = null;
            while (j.hasNext()) {
                parent = (DataObject) j.next();
                if (parent instanceof ProjectData) {
                    children = ((ProjectData) parent).getDatasets();
                } else if (parent instanceof DatasetData) {
                	children = new HashSet(1);
                	children.add(parent);
                } else if (parent instanceof TagAnnotationData) {
                	children = new HashSet(1);
                	children.add(parent);
                } else if (parent instanceof ScreenData) {
                	children = ((ScreenData) parent).getPlates();
                } else if (parent instanceof GroupData) {
                	children = ((GroupData) parent).getExperimenters();
                }
                map.put(parent, children);
            }
        } else map = (Map) result;
        node.setResults(map);
    }
    
    /**
     * Formats the results.
     * 
     * @param expId		The user's id.
     * @param result	The result of the call for the passed user.
     */
    private void formatSmartFolderResult(long expId, List result)
    {
    	RefreshExperimenterDef node = expNodes.get(expId);
    	List nodes = node.getExpandedNodes();
    	int n = nodes.size();
    	TreeImageSet display;
    	TimeRefObject ref;
    	Map m = new HashMap();
    	
    	for (int i = 0; i < n; i++) {
			display = (TreeImageSet) nodes.get(i);
			ref = (TimeRefObject) result.get(i);
			m.put(display, ref.getResults());
		}
    	node.setResults(m);
    }
    
    /**
     * Creates a new instance. 
     * 
     * @param viewer        The viewer this data loader is for.
     *                      Mustn't be <code>null</code>.
     * @param rootNodeType	The root node either <code>Project</code> or 
     *                      <code>Screen</code>.
     * @param expNodes		Collection of nodes hosting information about
     * 						the nodes to refresh.
     * 						Mustn't be <code>null</code>.
     * @param refNode		The node of reference.
     * @param toBrowse      The node to browse.
     */
    public RefreshExperimenterDataLoader(Browser viewer, 
    			Class rootNodeType, Map<Long, RefreshExperimenterDef> expNodes, 
    			Class type, long id, Object refNode, DataObject toBrowse)
    {
        super(viewer);
        if (expNodes == null || expNodes.size() == 0)
        	throw new IllegalArgumentException("Experimenter nodes not valid.");
        checkClass(rootNodeType);
        this.rootNodeType = rootNodeType;
        this.expNodes = expNodes;
        this.type = type;
        this.id = id;
        this.refNode = refNode;
        this.toBrowse = toBrowse;
    }
    
    /**
     * Retrieves the data.
     * @see DataBrowserLoader#load()
     */
    public void load()
    {
    	Entry entry;
    	Iterator i = expNodes.entrySet().iterator();
    	RefreshExperimenterDef def;
    	long userID;
    	TimeRefObject ref = null;
    	List nodes;
    	List<TimeRefObject> times;
    	Iterator j;
    	TreeImageSet node;
    	Map<Long, List> m = new HashMap<Long, List>(expNodes.size());
    	if (ImageData.class.equals(rootNodeType) || 
    			FileAnnotationData.class.equals(rootNodeType)) {
    		TreeImageTimeSet time;
    		TreeFileSet file;
    		while (i.hasNext()) {
    			entry = (Entry) i.next();
        		userID = (Long) entry.getKey();
        		def = (RefreshExperimenterDef) entry.getValue();
        		nodes = def.getExpandedNodes();
        		j = nodes.iterator();
        		times = new ArrayList<TimeRefObject>(nodes.size());
        		while (j.hasNext()) {
        			node = (TreeImageSet) j.next();
        			if (node instanceof TreeImageTimeSet) {
        				time = (TreeImageTimeSet) node;
        				ref = new TimeRefObject(userID, TimeRefObject.TIME);
            			ref.setTimeInterval(time.getStartTime(), 
            					time.getEndTime());
    					
        			} else if (node instanceof TreeFileSet) {
        				file = (TreeFileSet) node;
        				ref = new TimeRefObject(userID, TimeRefObject.FILE);
            			ref.setFileType(file.getType());
        			}
        			if (ref != null) times.add(ref);
				}
    			m.put(userID, times);
    		}
    	} else {
    		List l;
        	while (i.hasNext()) {
        		entry = (Entry) i.next();
        		userID = (Long) entry.getKey();
        		def = (RefreshExperimenterDef) entry.getValue();
        		if (GroupData.class.equals(rootNodeType)) {
        			l = (List) def.getExpandedTopNodes().get(GroupData.class);
        			if (l == null) l = new ArrayList();
        			m.put(userID, l);
        		} else m.put(userID, def.getExpandedNodes());
    		}
    	}
    	handle = dmView.refreshHierarchy(rootNodeType, m, this);
    }

    /**
     * Cancels the data loading.
     * @see DataBrowserLoader#cancel()
     */
    public void cancel() { handle.cancel(); }

    /**
     * Feeds the result back to the viewer.
     * @see DataBrowserLoader#handleResult(Object)
     */
    public void handleResult(Object result)
    {
        if (viewer.getState() == Browser.DISCARDED) return;  //Async cancel.
        if (GroupData.class.equals(rootNodeType)) {
        	Entry entry;
        	RefreshExperimenterDef def;
        	Iterator i = expNodes.entrySet().iterator();
        	Map nodes;
        	List l;
        	Iterator j;
        	while (i.hasNext()) {
				entry = (Entry) i.next();
				def = (RefreshExperimenterDef) entry.getValue();
        		nodes = def.getExpandedTopNodes();
        		viewer.setGroups((Collection) result, 
        				(List) nodes.get(GroupData.class));
			}
        	return;
        }
        Map m = (Map) result;
        Entry entry;
        Iterator i = m.entrySet().iterator();
        long expId;
        if (ImageData.class.equals(rootNodeType) || 
        		FileAnnotationData.class.equals(rootNodeType)) {
        	while (i.hasNext()) {
        		entry = (Entry) i.next();
            	expId = (Long) entry.getKey();
            	formatSmartFolderResult(expId, (List) entry.getValue());
    		}
        } else {
        	while (i.hasNext()) {
        		entry = (Entry) i.next();
            	expId = (Long) entry.getKey();
            	setExperimenterResult(expId, entry.getValue());
    		}
        }
        viewer.setRefreshExperimenterData(expNodes, type, id);
        if (refNode instanceof TreeImageDisplay || refNode == null)
        	viewer.browse((TreeImageDisplay) refNode, toBrowse, true);
    }

}
