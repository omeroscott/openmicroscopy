/*
 * org.openmicroscopy.shoola.agents.metadata.view.MetadataViewerComponent 
 *
 *------------------------------------------------------------------------------
 *  Copyright (C) 2006-2008 University of Dundee. All rights reserved.
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
package org.openmicroscopy.shoola.agents.metadata.view;


//Java imports
import java.awt.Color;
import java.awt.Component;
import java.awt.Cursor;
import java.awt.Dimension;
import java.awt.Point;
import java.awt.image.BufferedImage;
import java.beans.PropertyChangeEvent;
import java.beans.PropertyChangeListener;
import java.io.File;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Map.Entry;

import javax.swing.Icon;
import javax.swing.JComponent;
import javax.swing.JFrame;

//Third-party libraries

//Application-internal dependencies
import omero.model.OriginalFile;

import org.openmicroscopy.shoola.agents.events.iviewer.RndSettingsSaved;
import org.openmicroscopy.shoola.agents.metadata.IconManager;
import org.openmicroscopy.shoola.agents.metadata.MetadataViewerAgent;
import org.openmicroscopy.shoola.agents.metadata.RenderingControlLoader;
import org.openmicroscopy.shoola.agents.metadata.browser.Browser;
import org.openmicroscopy.shoola.agents.metadata.browser.TreeBrowserDisplay;
import org.openmicroscopy.shoola.agents.metadata.browser.TreeBrowserSet;
import org.openmicroscopy.shoola.agents.metadata.editor.Editor;
import org.openmicroscopy.shoola.agents.metadata.rnd.Renderer;
import org.openmicroscopy.shoola.agents.metadata.util.ChannelSelectionDialog;
import org.openmicroscopy.shoola.agents.treeviewer.TreeViewerAgent;
import org.openmicroscopy.shoola.agents.util.EditorUtil;
import org.openmicroscopy.shoola.agents.util.DataObjectRegistration;
import org.openmicroscopy.shoola.agents.util.ui.MovieExportDialog;
import org.openmicroscopy.shoola.env.config.Registry;
import org.openmicroscopy.shoola.env.data.model.AdminObject;
import org.openmicroscopy.shoola.env.data.model.AnalysisParam;
import org.openmicroscopy.shoola.env.data.model.DeletableObject;
import org.openmicroscopy.shoola.env.data.model.DeleteActivityParam;
import org.openmicroscopy.shoola.env.data.model.DownloadActivityParam;
import org.openmicroscopy.shoola.env.data.model.MovieActivityParam;
import org.openmicroscopy.shoola.env.data.model.MovieExportParam;
import org.openmicroscopy.shoola.env.data.model.FigureParam;
import org.openmicroscopy.shoola.env.data.model.ScriptActivityParam;
import org.openmicroscopy.shoola.env.data.model.ScriptObject;
import org.openmicroscopy.shoola.env.data.util.StructuredDataResults;
import org.openmicroscopy.shoola.env.event.EventBus;
import org.openmicroscopy.shoola.env.log.LogMessage;
import org.openmicroscopy.shoola.env.rnd.RndProxyDef;
import org.openmicroscopy.shoola.env.ui.UserNotifier;
import org.openmicroscopy.shoola.util.ui.UIUtilities;
import org.openmicroscopy.shoola.util.ui.component.AbstractComponent;
import pojos.AnnotationData;
import pojos.ChannelData;
import pojos.DataObject;
import pojos.DatasetData;
import pojos.ExperimenterData;
import pojos.FileAnnotationData;
import pojos.FileData;
import pojos.ImageData;
import pojos.PixelsData;
import pojos.PlateAcquisitionData;
import pojos.PlateData;
import pojos.ProjectData;
import pojos.ScreenData;
import pojos.TagAnnotationData;
import pojos.WellData;
import pojos.WellSampleData;

/** 
 * Implements the {@link MetadataViewer} interface to provide the functionality
 * required of the hierarchy viewer component.
 * This class is the component hub and embeds the component's MVC triad.
 * It manages the component's state machine and fires state change 
 * notifications as appropriate, but delegates actual functionality to the
 * MVC sub-components.
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
class MetadataViewerComponent 
	extends AbstractComponent
	implements MetadataViewer
{
	
	/** The Model sub-component. */
	private MetadataViewerModel 	model;
	
	/** The Control sub-component. */
	private MetadataViewerControl	controller;
	
	/** The View sub-component. */
	private MetadataViewerUI 		view;
	
	/**
	 * Creates the movie.
	 * 
	 * @param parameters The parameters used to create the movie.
	 */
	private void createMovie(MovieExportParam parameters)
	{
		if (parameters == null) return;
		Object refObject = model.getRefObject();
		ImageData img = null;
		if (refObject instanceof ImageData)
			img = (ImageData) refObject;
		else if (refObject instanceof WellSampleData) {
			img = ((WellSampleData) refObject).getImage();
		}
		if (img == null) return;
		UserNotifier un = MetadataViewerAgent.getRegistry().getUserNotifier();
		MovieActivityParam activity = new MovieActivityParam(parameters, null,
				img);
		IconManager icons = IconManager.getInstance();
		activity.setIcon(icons.getIcon(IconManager.MOVIE_22));
		un.notifyActivity(activity);
	}

	/**
	 * Deletes the annotations.
	 * 
	 * @param toDelete The annotations to delete.
	 */
	private void deleteAnnotations(List<AnnotationData> toDelete)
	{
		if (toDelete == null || toDelete.size() == 0) return;
		//Should only be annotation so content is false;
		List<DeletableObject> l = new ArrayList<DeletableObject>();
		Iterator<AnnotationData> j = toDelete.iterator();
		while (j.hasNext())
			l.add(new DeletableObject(j.next()));
		IconManager icons = IconManager.getInstance();
		DeleteActivityParam p = new DeleteActivityParam(
				icons.getIcon(IconManager.APPLY_22), l);
		p.setFailureIcon(icons.getIcon(IconManager.DELETE_22));
		UserNotifier un = 
			TreeViewerAgent.getRegistry().getUserNotifier();
		un.notifyActivity(p);
	}
	
	/**
	 * Creates a new instance.
	 * The {@link #initialize() initialize} method should be called straight
	 * after to complete the MVC set up.
	 * 
	 * @param model The Model sub-component. Mustn't be <code>null</code>.
	 */
	MetadataViewerComponent(MetadataViewerModel model)
	{
		if (model == null) throw new NullPointerException("No model.");
		this.model = model;
		controller = new MetadataViewerControl();
		view = new MetadataViewerUI();
	}
	
	/** Links up the MVC triad. */
	void initialize()
	{
		controller.initialize(this, view);
		view.initialize(controller, model);
		if (!(model.getRefObject() instanceof String))
			setSelectionMode(true);
	}

	/** Saves before close. */
	void saveBeforeClose()
	{
		firePropertyChange(SAVE_DATA_PROPERTY, Boolean.valueOf(true), 
				Boolean.valueOf(false));
	}
	
	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#activate(Map)
	 */
	public void activate(Map channelData)
	{
		switch (model.getState()) {
			case NEW:
				model.getEditor().setChannelsData(channelData, false);
				setRootObject(model.getRefObject(), model.getUserID());
				break;
			case DISCARDED:
				throw new IllegalStateException(
					"This method can't be invoked in the DISCARDED state.");
		} 
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#discard()
	 */
	public void discard()
	{
		model.discard();
		fireStateChange();
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getState()
	 */
	public int getState() { return model.getState(); }

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#cancel(TreeBrowserDisplay)
	 */
	public void cancel(TreeBrowserDisplay refNode) { model.cancel(refNode); }

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#loadMetadata(TreeBrowserDisplay)
	 */
	public void loadMetadata(TreeBrowserDisplay node)
	{
		if (model.getState() == DISCARDED)
			throw new IllegalStateException(
					"This method cannot be invoked in the DISCARDED state.");
		if (node == null)
			throw new IllegalArgumentException("No node specified.");
		Object userObject = node.getUserObject();
		if (userObject instanceof DataObject) {
			if (model.isSingleMode()) {
				model.fireStructuredDataLoading(node);
				fireStateChange();
			}
		} else if (userObject instanceof File) {
			File f = (File) userObject;
			if (f.isDirectory() && model.isSingleMode()) {
				model.fireStructuredDataLoading(node);
				fireStateChange();
			}
		}
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setMetadata(TreeBrowserDisplay, Object)
	 */
	public void setMetadata(TreeBrowserDisplay node, Object result)
	{
		if (node == null)
			throw new IllegalArgumentException("No node specified.");
		Object userObject = node.getUserObject();
		Object refObject = model.getRefObject();
		if (refObject == userObject) {
			Browser browser = model.getBrowser();
			if (result instanceof StructuredDataResults) {
				model.setStructuredDataResults((StructuredDataResults) result);
				browser.setParents(node, 
						model.getStructuredData().getParents());
				model.getEditor().setStructuredDataResults();
				view.setOnScreen();
				fireStateChange();
				return;
			}
			if (!(userObject instanceof String)) return;
			String name = (String) userObject;
			
			if (browser == null) return;
			if (Browser.DATASETS.equals(name) || Browser.PROJECTS.equals(name)) 
				browser.setParents((TreeBrowserSet) node, (Collection) result);
			model.notifyLoadingEnd(node);
		}
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getSelectionUI()
	 */
	public JComponent getSelectionUI()
	{
		if (model.getState() == DISCARDED)
			throw new IllegalStateException("This method cannot be invoked " +
					"in the DISCARDED state.");
		return model.getBrowser().getUI();
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getEditorUI()
	 */
	public JComponent getEditorUI()
	{
		if (model.getState() == DISCARDED)
			throw new IllegalStateException("This method cannot be invoked " +
					"in the DISCARDED state.");
		return model.getEditor().getUI();
	}
	
	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getUI()
	 */
	public JComponent getUI()
	{
		if (model.getState() == DISCARDED)
			throw new IllegalStateException("This method cannot be invoked " +
					"in the DISCARDED state.");
		return view.getUI();
	}
	
	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setRootObject(Object, long)
	 */
	public void setRootObject(Object root, long userID)
	{
		if (root instanceof WellSampleData) {
			WellSampleData ws = (WellSampleData) root;
			if (ws.getId() < 0) root = null;
		}
		if (root == null) {
			root = "";
			userID = -1;
		}
		//Previewed the image.
		Renderer rnd = model.getEditor().getRenderer();
		if (rnd != null && getRndIndex() == RND_GENERAL) {
			//save settings 
			long imageID = -1;
			long pixelsID = -1;
			Object obj = model.getRefObject();
			if (obj instanceof WellSampleData) {
				WellSampleData wsd = (WellSampleData) obj;
				obj = wsd.getImage();
			}
			if (obj instanceof ImageData) {
				ImageData data = (ImageData) obj;
				imageID = data.getId();
				pixelsID = data.getDefaultPixels().getId();
			}
			//check if I can save first
			/*
			if (model.isWritable()) {
				Registry reg = MetadataViewerAgent.getRegistry();
				RndProxyDef def = null;
				try {
					def = rnd.saveCurrentSettings();
				} catch (Exception e) {
					try {
						reg.getImageService().resetRenderingService(pixelsID);
						def = rnd.saveCurrentSettings();
					} catch (Exception ex) {
						String s = "Data Retrieval Failure: ";
				    	LogMessage msg = new LogMessage();
				        msg.print(s);
				        msg.print(e);
				        reg.getLogger().error(this, msg);
					}
				}
				EventBus bus = 
					MetadataViewerAgent.getRegistry().getEventBus();
				bus.post(new RndSettingsSaved(pixelsID, def));
			}
			
			if (imageID >= 0 && model.isWritable()) {
				firePropertyChange(RENDER_THUMBNAIL_PROPERTY, -1, imageID);
			}
			*/
		}
		model.setRootObject(root);
		view.setRootObject();
		//reset the parent.
		model.setUserID(userID);
		setParentRootObject(null, null);
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setParentRootObject(Object, Object)
	 */
	public void setParentRootObject(Object parent, Object grandParent)
	{
		model.setParentRootObject(parent, grandParent);
	}
	
	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#loadContainers(TreeBrowserDisplay)
	 */
	public void loadContainers(TreeBrowserDisplay node)
	{
		if (node == null)
			throw new IllegalArgumentException("No node specified.");
		model.fireParentLoading((TreeBrowserSet) node);
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setContainers(TreeBrowserDisplay, Object)
	 */
	public void setContainers(TreeBrowserDisplay node, Object result)
	{
		Browser browser = model.getBrowser();
		if (node == null) {
			StructuredDataResults data = model.getStructuredData();
			if (data != null) {
				data.setParents((Collection) result);
				browser.setParents(null, (Collection) result);
			}
		} else
			browser.setParents((TreeBrowserSet) node, (Collection) result);
		model.getEditor().setStatus(false);
	}
	
	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getRelatedNodes()
	 */
	public List getRelatedNodes()
	{
		return model.getRelatedNodes();
	}
	
	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#saveData(List, List, List, List, DataObject, boolean)
	 */
	public void saveData(List<AnnotationData> toAdd, 
				List<AnnotationData> toRemove, List<AnnotationData> toDelete,
				List<Object> metadata, DataObject data, boolean asynch)
	{
		if (data == null) return;
		Object refObject = model.getRefObject();
		List<DataObject> toSave = new ArrayList<DataObject>();
		if (refObject instanceof FileData) {
			FileData fa = (FileData) data;
			if (fa.getId() > 0) {
				toSave.add(data);
				model.fireSaving(toAdd, toRemove, metadata, toSave, asynch);
				fireStateChange();
				deleteAnnotations(toDelete);
			} else {
				DataObjectRegistration r = new DataObjectRegistration(toAdd, 
						toRemove, toDelete, metadata, data);
				firePropertyChange(REGISTER_PROPERTY, null, r);
				return;
			}
			return;
		}
		Collection nodes = model.getRelatedNodes();
		Iterator n;
		toSave.add(data);
		if (!model.isSingleMode()) {
			if (nodes != null) {
				n = nodes.iterator();
				while (n.hasNext()) 
					toSave.add((DataObject) n.next());
			}
		}
		boolean b = true;
		if (refObject instanceof ProjectData || 
			refObject instanceof ScreenData ||
			refObject instanceof PlateData || 
			refObject instanceof DatasetData || 
			refObject instanceof WellSampleData ||
			refObject instanceof PlateAcquisitionData ||
			refObject instanceof WellData) {
			model.fireSaving(toAdd, toRemove, metadata, toSave, asynch);
		} else if (refObject instanceof ImageData) {
			ImageData img = (ImageData) refObject;
			if (img.getId() < 0) {
				DataObjectRegistration r = new DataObjectRegistration(toAdd, 
						toRemove, toDelete, metadata, data);
				firePropertyChange(REGISTER_PROPERTY, null, r);
				return;
			} else {
				model.fireSaving(toAdd, toRemove, metadata, toSave,
						asynch);
			}
		}  else if (refObject instanceof TagAnnotationData) {
			//Only update properties.
			if ((toAdd.size() == 0 && toRemove.size() == 0)) {
				model.fireSaving(toAdd, toRemove, metadata, toSave, asynch);
				b = false;
			}	
		}
		if (toDelete != null && toDelete.size() > 0)
			deleteAnnotations(toDelete);
		if (b) fireStateChange();
	}
	
	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#hasDataToSave()
	 */
	public boolean hasDataToSave()
	{
		Editor editor = model.getEditor();
		if (editor == null) return false;
		return editor.hasDataToSave();
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#saveData()
	 */
	public void saveData()
	{
		firePropertyChange(SAVE_DATA_PROPERTY, Boolean.valueOf(false), 
				Boolean.valueOf(true));
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#clearDataToSave()
	 */
	public void clearDataToSave()
	{
		firePropertyChange(CLEAR_SAVE_DATA_PROPERTY, Boolean.FALSE, 
							Boolean.TRUE);
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#onDataSave(List)
	 */
	public void onDataSave(List<DataObject> data)
	{
		if (data == null) return;
		if (model.getState() == DISCARDED) return;
		DataObject dataObject = null;
		if (data.size() == 1) dataObject = data.get(0);
		if (dataObject != null && model.isSameObject(dataObject)) {
			setRootObject(model.getRefObject(), model.getUserID());
			firePropertyChange(ON_DATA_SAVE_PROPERTY, null, dataObject);
		} else
			firePropertyChange(ON_DATA_SAVE_PROPERTY, null, data);
		model.setState(READY);
		view.setCursor(Cursor.getPredefinedCursor(Cursor.DEFAULT_CURSOR));
		fireStateChange();
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setSelectionMode(boolean)
	 */
	public void setSelectionMode(boolean single)
	{
		model.setSelectionMode(single);
		model.getEditor().setSelectionMode(single);
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#isSingleMode()
	 */
	public boolean isSingleMode()
	{
		return model.isSingleMode();
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setRelatedNodes(List)
	 */
	public void setRelatedNodes(List nodes)
	{
		setRootObject(model.getRefObject(), model.getUserID());
		model.setRelatedNodes(nodes);
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#onAdminUpdated(Object)
	 */
	public void onAdminUpdated(Object data)
	{
		Object o = data;
		if (data instanceof Map) {
			Map l = (Map) data;
			if (l.size() > 0) {
				UserNotifier un = 
					MetadataViewerAgent.getRegistry().getUserNotifier();
				StringBuffer buf = new StringBuffer();
				buf.append("Unable to update the following experimenters:\n");
				Entry entry;
				Iterator i = l.entrySet().iterator();
				Object node;
				ExperimenterData exp;
				Exception ex;
				while (i.hasNext()) {
					entry = (Entry) i.next();
					node = entry.getKey();
					if (node instanceof ExperimenterData) {
						exp = (ExperimenterData) node;
						ex = (Exception) entry.getValue();
						buf.append(exp.getFirstName()+" "+exp.getLastName());
						buf.append("\n->"+ex.getMessage());
						buf.append("\n");
					}
				}
				un.notifyInfo("Update experimenters", buf.toString());
			}
			firePropertyChange(CLEAR_SAVE_DATA_PROPERTY, null, data);
			setRootObject(null, -1);
		} else setRootObject(o, model.getUserID());
		firePropertyChange(ADMIN_UPDATED_PROPERTY, null, data);
		
		/*
		if (data instanceof ExperimenterData || data instanceof GroupData) {
			firePropertyChange(ADMIN_UPDATED_PROPERTY, null, data);
			setRootObject(data, model.getUserID());
		}
		*/
		
	}
	
	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#loadParents()
	 */
	public void loadParents()
	{
		StructuredDataResults data = model.getStructuredData();
		if (data == null) return;
		if (data.getParents() != null) return;
		Object ho = data.getRelatedObject();
		if (ho != null && ho instanceof DataObject) {
			model.loadParents(ho.getClass(), ((DataObject) ho).getId());
			setStatus(true);
			firePropertyChange(LOADING_PARENTS_PROPERTY, Boolean.FALSE, 
					Boolean.TRUE);
		}
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getStructuredData()
	 */
	public StructuredDataResults getStructuredData()
	{
		//TODO: Check state
		return model.getStructuredData();
	}

	/** 
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setStatus(boolean)
	 */
	public void setStatus(boolean busy)
	{
		model.getEditor().setStatus(busy);
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#showTagWizard()
	 */
	public void showTagWizard()
	{
		if (model.getState() == DISCARDED) return;
		model.getEditor().loadExistingTags();
		//model.getMetadataViewer().showTagWizard();
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getObjectPath()
	 */
	public String getObjectPath()
	{
		return model.getRefObjectPath();
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#makeMovie(int, Color)
	 */
	public void makeMovie(int scaleBar, Color overlayColor)
	{
		Object refObject = model.getRefObject();
		if (refObject instanceof WellSampleData) {
			WellSampleData wsd = (WellSampleData) refObject;
			refObject = wsd.getImage();
		}
		if (!(refObject instanceof ImageData)) return;
		PixelsData data = null;
		ImageData img = (ImageData) refObject;
    	try {
    		data = ((ImageData) refObject).getDefaultPixels();
		} catch (Exception e) {}
		if (data == null) return;
		int maxT = data.getSizeT();
    	int maxZ = data.getSizeZ();
    	int defaultZ = maxZ;
    	int defaultT = maxT;
    	String name = EditorUtil.getPartialName(img.getName());
    	JFrame f = MetadataViewerAgent.getRegistry().getTaskBar().getFrame();
    	MovieExportDialog dialog = new MovieExportDialog(f, name, 
    			maxT, maxZ, defaultZ, defaultT);
    	dialog.setBinaryAvailable(MetadataViewerAgent.isBinaryAvailable());
    	dialog.setScaleBarDefault(scaleBar, overlayColor);
    	dialog.addPropertyChangeListener(new PropertyChangeListener() {
		
			public void propertyChange(PropertyChangeEvent evt) {
				String name = evt.getPropertyName();
				if (MovieExportDialog.CREATE_MOVIE_PROPERTY.equals(name)) {
					Object src = evt.getSource();
					if (src instanceof MovieExportDialog) {
						MovieExportDialog d = (MovieExportDialog) src;
						createMovie(d.getParameters());
					}
				}
			}
		});
		dialog.centerDialog();
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#uploadMovie(FileAnnotationData, File)
	 */
	public void uploadMovie(FileAnnotationData data, File folder)
	{
		UserNotifier un = MetadataViewerAgent.getRegistry().getUserNotifier();
		if (data == null) {
			if (folder == null) 
				un.notifyInfo("Movie Creation", "A problem occured while " +
					"creating the movie");
		} else {
			if (folder == null) folder = UIUtilities.getDefaultFolder();
			OriginalFile f = (OriginalFile) data.getContent();
			IconManager icons = IconManager.getInstance();
			
			DownloadActivityParam activity = new DownloadActivityParam(f,
					folder, icons.getIcon(IconManager.DOWNLOAD_22));
			un.notifyActivity(activity);
			//un.notifyDownload(data, folder);
		}
		firePropertyChange(CREATING_MOVIE_PROPERTY, Boolean.valueOf(true), 
				Boolean.valueOf(false));
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getRndIndex()
	 */
	public int getRndIndex()
	{
		if (model.getState() == MetadataViewer.DISCARDED) return -1;
		return model.getIndex();
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#renderPlane()
	 */
	public void renderPlane()
	{
		Object obj = model.getRefObject();
		if (obj instanceof WellSampleData) {
			WellSampleData wsd = (WellSampleData) obj;
			obj = wsd.getImage();
		}
		if (!(obj instanceof ImageData)) return;
		long imageID = ((ImageData) obj).getId();
		switch (getRndIndex()) {
			case RND_GENERAL:
				model.getEditor().getRenderer().renderPreview();
				//firePropertyChange(RENDER_THUMBNAIL_PROPERTY, -1, imageID);
				break;
			case RND_SPECIFIC:
				firePropertyChange(RENDER_PLANE_PROPERTY, -1, imageID);
			break;
		}
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#applyToAll()
	 */
	public void applyToAll()
	{
		Object obj = model.getRefObject();
		if (obj instanceof ImageData) {
			firePropertyChange(APPLY_SETTINGS_PROPERTY, null, obj);
		} else if (obj instanceof WellSampleData) {
			Object[] objects = new Object[2];
			objects[0] = obj;
			objects[1] = model.getParentRefObject();
			firePropertyChange(APPLY_SETTINGS_PROPERTY, null, objects);
		}
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#onSettingsApplied()
	 */
	public void onSettingsApplied()
	{
		firePropertyChange(SETTINGS_APPLIED_PROPERTY, Boolean.valueOf(false), 
				Boolean.valueOf(true));
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#onRndLoaded(boolean)
	 */
	public void onRndLoaded(boolean reload)
	{
		getRenderer().addPropertyChangeListener(controller);
		firePropertyChange(RND_LOADED_PROPERTY, Boolean.valueOf(!reload), 
				Boolean.valueOf(reload));
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getRenderer()
	 */
	public Renderer getRenderer()
	{
		if (model.getEditor() == null) return null;
		return model.getEditor().getRenderer();
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#onChannelSelected(int)
	 */
	public void onChannelSelected(int index)
	{
		if (getRndIndex() != RND_SPECIFIC) return;
		firePropertyChange(SELECTED_CHANNEL_PROPERTY, -1, index);
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getIdealRendererSize()
	 */
	public Dimension getIdealRendererSize()
	{
		Renderer rnd = getRenderer();
		if (rnd == null) return new Dimension(0, 0);
		return rnd.getUI().getPreferredSize();
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#analyse(int)
	 */
	public void analyse(int index)
	{
		if (index != AnalysisParam.FRAP) return;
		Object refObject = model.getRefObject();
		if (!(refObject instanceof ImageData)) return;
		List<ChannelData> channels = new ArrayList<ChannelData>();
		Map m = model.getEditor().getChannelData();
		if (m != null && m.size() == 1) {
			controller.analyseFRAP(0);
			return;
		}
		if (m != null) {
			Iterator j = m.keySet().iterator();
			while (j.hasNext()) {
				channels.add((ChannelData) j.next());
			}
		}
		
		IconManager icons = IconManager.getInstance();
		Icon icon = icons.getIcon(IconManager.ANALYSE_48);
		switch (index) {
			case AnalysisParam.FRAP:
				icon = icons.getIcon(IconManager.ANALYSE_FRAP_48);
				break;
		}
		JFrame f = MetadataViewerAgent.getRegistry().getTaskBar().getFrame();
		ChannelSelectionDialog d = new ChannelSelectionDialog(f, icon, channels,
				index);
		d.addPropertyChangeListener(controller);
		UIUtilities.centerAndShow(d);
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#uploadFret(FileAnnotationData, File)
	 */
	public void uploadFret(FileAnnotationData data, File folder)
	{
		UserNotifier un = MetadataViewerAgent.getRegistry().getUserNotifier();
		if (data == null) {
			if (folder == null) 
				un.notifyInfo("Data Analysis", "A problem occured while " +
					"analyzing the data.");
		} else {
			if (folder == null) folder = UIUtilities.getDefaultFolder();
			OriginalFile f = (OriginalFile) data.getContent();
			IconManager icons = IconManager.getInstance();
			
			DownloadActivityParam activity = new DownloadActivityParam(f,
					folder, icons.getIcon(IconManager.DOWNLOAD_22));
			un.notifyActivity(activity);
		}
		firePropertyChange(ANALYSE_PROPERTY, Boolean.valueOf(true), 
				Boolean.valueOf(false));
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#onRndSettingsCopied(Collection)
	 */
	public void onRndSettingsCopied(Collection imageIds)
	{
		if (imageIds == null || imageIds.size() == 0) return;
		Renderer rnd = getRenderer();
		if (rnd == null) return;
		Object ob = model.getRefObject();
		ImageData img = null;
		if (ob instanceof WellSampleData) {
			WellSampleData wsd = (WellSampleData) ob;
			img = wsd.getImage();
		} else if (ob instanceof ImageData)
			img = (ImageData) ob;
		if (img == null) return;
		if (!imageIds.contains(img.getId())) return;
		rnd.refresh();
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#isNumerousChannel()
	 */
	public boolean isNumerousChannel() { return model.isNumerousChannel(); }

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setSelectedTab(int)
	 */
	public void setSelectedTab(int index)
	{
		model.getEditor().setSelectedTab(index);
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#activityOptions(Component, Point, int)
	 */
	public void activityOptions(Component source, Point location, int index)
	{
		List<Object> l = new ArrayList<Object>();
		l.add(source);
		l.add(location);
		l.add(index);
		firePropertyChange(ACTIVITY_OPTIONS_PROPERTY, null, l);
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#createFigure(Object)
	 */
	public void createFigure(Object value)
	{
		if (value == null) return;
		if (value instanceof FigureParam)
			firePropertyChange(GENERATE_FIGURE_PROPERTY, null, value);
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#manageScript(ScriptObject, int)
	 */
	public void manageScript(ScriptObject value, int index)
	{
		if (value == null) return;
		ScriptActivityParam p = null;
		switch (index) {
			case RUN:
				p = new ScriptActivityParam(value, ScriptActivityParam.RUN);
				break;
			case DOWNLOAD:
				p = new ScriptActivityParam(value, 
						ScriptActivityParam.DOWNLOAD);
				break;
			case VIEW:
				p = new ScriptActivityParam(value, ScriptActivityParam.VIEW);
				break;
		}
		if (p != null)
			firePropertyChange(HANDLE_SCRIPT_PROPERTY, null, p);
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#reloadRenderingControl(Boolean)
	 */
	public void reloadRenderingControl(boolean value)
	{
		if (value)
			model.getEditor().loadRenderingControl(
					RenderingControlLoader.RELOAD);
		else {
			firePropertyChange(CLOSE_RENDERER_PROPERTY, null, 
					model.getRefObject());
		}
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#onChannelColorChanged(int)
	 */
	public void onChannelColorChanged(int index)
	{
		view.onChannelColorChanged(index);
		firePropertyChange(CHANNEL_COLOR_CHANGED_PROPERTY, -1, index);
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getRefObject()
	 */
	public Object getRefObject() { return model.getRefObject(); }

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#updateAdminObject(Object, boolean)
	 */
	public void updateAdminObject(Object data, boolean async)
	{
		if (data instanceof ExperimenterData) {
			model.fireExperimenterSaving((ExperimenterData) data, async);
		} else if (data instanceof AdminObject)
			model.fireAdminSaving((AdminObject) data, async);
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#getUserID()
	 */
	public long getUserID() { return model.getUserID(); }
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#resetPassword(String)
	 */
	public void resetPassword(String newPass)
	{
		firePropertyChange(RESET_PASSWORD_PROPERTY, null, newPass);
	}

	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#loadViewedBy()
	 */
	public void loadViewedBy()
	{
		Object ref = model.getRefObject();
		if (ref instanceof ImageData || ref instanceof WellSampleData) {
			if (model.getViewedBy() != null) setViewedBy(model.getViewedBy());
			else model.fireViewedByLoading();
		}
	}
	
	/**
	 * Implemented as specified by the {@link MetadataViewer} interface.
	 * @see MetadataViewer#setViewedBy(map)
	 */
	public void setViewedBy(Map result)
	{
		model.setViewedBy(result);
		view.viewedBy();
		model.fireThumbnailsLoading();
	}
	
	/** 
	 * Implemented as specified by the {@link Editor} interface.
	 * @see MetadataViewer#setThumbnails(Map, long)
	 */
	public void setThumbnails(Map<Long, BufferedImage> thumbnails, 
							long imageID)
	{
		Object ref = model.getRefObject();
		ImageData image = null;
		if (ref instanceof ImageData) image = (ImageData) ref;
		else if (ref instanceof WellSampleData) 
			image = ((WellSampleData) ref).getImage();
		
		if (image == null) return;
		if (image.getId() == imageID) {
			view.setThumbnails(thumbnails);
		}
	}
	
	/** 
	 * Implemented as specified by the {@link Editor} interface.
	 * @see MetadataViewer#uploadScript()
	 */
	public void uploadScript()
	{
		firePropertyChange(UPLOAD_SCRIPT_PROPERTY, Boolean.valueOf(false), 
				Boolean.valueOf(true));
	}
	
	/** Saves the settings. */
	public void saveSettings() 
	{
		//Previewed the image.
		Renderer rnd = model.getEditor().getRenderer();
		if (rnd != null && getRndIndex() == RND_GENERAL) {
			//save settings 
			long imageID = -1;
			long pixelsID = -1;
			Object obj = model.getRefObject();
			if (obj instanceof WellSampleData) {
				WellSampleData wsd = (WellSampleData) obj;
				obj = wsd.getImage();
			}
			if (obj instanceof ImageData) {
				ImageData data = (ImageData) obj;
				imageID = data.getId();
				pixelsID = data.getDefaultPixels().getId();
			}
			//check if I can save first
			if (model.isWritable()) {
				Registry reg = MetadataViewerAgent.getRegistry();
				RndProxyDef def = null;
				try {
					def = rnd.saveCurrentSettings();
				} catch (Exception e) {
					try {
						reg.getImageService().resetRenderingService(pixelsID);
						def = rnd.saveCurrentSettings();
					} catch (Exception ex) {
						String s = "Data Retrieval Failure: ";
				    	LogMessage msg = new LogMessage();
				        msg.print(s);
				        msg.print(e);
				        reg.getLogger().error(this, msg);
					}
				}
				EventBus bus = 
					MetadataViewerAgent.getRegistry().getEventBus();
				bus.post(new RndSettingsSaved(pixelsID, def));
			}
			
			if (imageID >= 0 && model.isWritable()) {
				firePropertyChange(RENDER_THUMBNAIL_PROPERTY, -1, imageID);
			}
		}	
	}
    
	/** 
	 * Overridden to return the name of the instance to save. 
	 * @see #toString()
	 */
	public String toString() { return model.getRefObjectName(); }

}
