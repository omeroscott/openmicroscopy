/*
 * org.openmicroscopy.shoola.agents.dataBrowser.actions.CreateExperimentAction 
 *
 *------------------------------------------------------------------------------
 *  Copyright (C) 2006-2009 University of Dundee. All rights reserved.
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
package org.openmicroscopy.shoola.agents.dataBrowser.actions;



//Java imports
import java.awt.event.ActionEvent;
import java.util.Collection;

import javax.swing.Action;

//Third-party libraries

//Application-internal dependencies
import org.openmicroscopy.shoola.agents.dataBrowser.IconManager;
import org.openmicroscopy.shoola.agents.dataBrowser.browser.Browser;
import org.openmicroscopy.shoola.agents.dataBrowser.browser.ImageDisplay;
import org.openmicroscopy.shoola.agents.dataBrowser.view.DataBrowser;
import org.openmicroscopy.shoola.util.ui.UIUtilities;

import pojos.DatasetData;
import pojos.ImageData;
import pojos.PlateData;
import pojos.ProjectData;
import pojos.ScreenData;

/** 
 * Action to launch the editor to create a new experiment.
 *
 * @author  Jean-Marie Burel &nbsp;&nbsp;&nbsp;&nbsp;
 * <a href="mailto:j.burel@dundee.ac.uk">j.burel@dundee.ac.uk</a>
 * @author Donald MacDonald &nbsp;&nbsp;&nbsp;&nbsp;
 * <a href="mailto:donald@lifesci.dundee.ac.uk">donald@lifesci.dundee.ac.uk</a>
 * @version 3.0
 * <small>
 * (<b>Internal version:</b> $Revision: $Date: $)
 * </small>
 * @since 3.0-Beta4
 */
public class CreateExperimentAction 
	extends DataBrowserAction
{

	/** The default name of the action. */
    private static final String NAME = "New Experiment...";

	/** The description of the action. */
	private static final String DESCRIPTION = "Launch the Editor.";
	
    /**
     * Sets the action enabled depending on the currently selected display
     * @see DataBrowserAction#onDisplayChange(ImageDisplay)
     */
    protected void onDisplayChange(ImageDisplay node)
    {
    	if (node == null) {
            setEnabled(false);
            return;
        }
    	Browser browser = model.getBrowser();
    	Collection l = browser.getSelectedDisplays();
    	if (l != null && l.size() == 1) {
    		Object object = node.getHierarchyObject();
    		if (object instanceof ImageData || object instanceof DatasetData ||
    			object instanceof ProjectData || object instanceof ScreenData ||
    			object instanceof PlateData)
    		setEnabled(model.isWritable(object));
    	}
    }
    
    /**
     * Creates a new instance.
     * 
     * @param model Reference to the Model. Mustn't be <code>null</code>.
     */
	public CreateExperimentAction(DataBrowser model)
	{
		super(model);
		putValue(Action.NAME, NAME);
		putValue(Action.SHORT_DESCRIPTION, 
				UIUtilities.formatToolTipText(DESCRIPTION));
		IconManager im = IconManager.getInstance();
		putValue(Action.SMALL_ICON, im.getIcon(IconManager.EDITOR));
	}
	
	
	/**
	 * Posts an event to create a new experiment.
	 * @see java.awt.event.ActionListener#actionPerformed(ActionEvent)
	 */
    public void actionPerformed(ActionEvent e) { model.createNewExperiment(); }
	
}
