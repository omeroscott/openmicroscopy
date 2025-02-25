/*
 * org.openmicroscopy.shoola.env.ui.ExportActivity
 *
 *------------------------------------------------------------------------------
 *  Copyright (C) 2006-2010 University of Dundee. All rights reserved.
 *
 *
 * 	This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 *  GNU General Public License for more details.
 *  
 *  You should have received a copy of the GNU General Public License along
 *  with this program; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 *------------------------------------------------------------------------------
 */
package org.openmicroscopy.shoola.env.ui;


//Java imports
import java.io.File;

//Third-party libraries

//Application-internal dependencies
import org.openmicroscopy.shoola.env.config.Registry;
import org.openmicroscopy.shoola.env.data.model.ExportActivityParam;
import org.openmicroscopy.shoola.util.filter.file.OMETIFFFilter;


/**
 * Activity to export an image.
 *
 * @author Jean-Marie Burel &nbsp;&nbsp;&nbsp;&nbsp;
 *         <a href="mailto:j.burel@dundee.ac.uk">j.burel@dundee.ac.uk</a>
 * @author Donald MacDonald &nbsp;&nbsp;&nbsp;&nbsp;
 *         <a href="mailto:donald@lifesci.dundee.ac.uk">donald@lifesci.dundee.ac.uk</a>
 * @version 3.0
 * <small>
 * (<b>Internal version:</b> $Revision: $Date: $)
 * </small>
 * @since 3.0-Beta4
 */
public class ExportActivity 
	extends ActivityComponent
{

	/** The description of the activity. */
	private static final String		CREATION_AS_XML = "Export image as XML";
	
	/** The description of the activity if OME-TIFF. */
	private static final String		CREATION_AS_OME_TIFF =
		"Export image as OME-TIFF";
	
	/** The description of the activity when finished. */
	private static final String		DESCRIPTION_CREATED = "Image exported";
	
	/** The description of the activity when cancelled. */
	private static final String		DESCRIPTION_CANCEL = "Export cancelled";
	
    /** The parameters hosting information about the image to export. */
    private ExportActivityParam parameters;
    
    /**
     * Returns the name of the file. 
     * 
     * @return See above.
     */
    private String getFileName()
    {
    	File folder = parameters.getFolder();
		String extension = "";
		String path = folder.getAbsolutePath();
		switch (parameters.getIndex()) {
			case ExportActivityParam.EXPORT_AS_OME_TIFF:
				if (!path.endsWith(OMETIFFFilter.OME_TIF) ||
					!path.endsWith(OMETIFFFilter.OME_TIFF))
					extension = "."+OMETIFFFilter.OME_TIFF;
				break;
		}
		//
		File parent = folder.getParentFile();
		String name = folder.getAbsolutePath();
		if (parent != null) {
			name = getFileName(parent.listFiles(), folder.getName()+extension, 
					folder.getName()+extension, 
					parent.getAbsolutePath()+File.separator, 1, extension);
			return parent+File.separator+name;
		}
		
    	return name+extension;
    }
    
    /**
     * Creates a new instance.
     * 
     * @param viewer		The viewer this data loader is for.
     *               		Mustn't be <code>null</code>.
     * @param registry		Convenience reference for subclasses.
     * @param parameters  	The parameters used to export the image.
     */
	public ExportActivity(UserNotifier viewer, Registry registry,
			ExportActivityParam parameters)
	{
		super(viewer, registry);
		if (parameters == null)
			throw new IllegalArgumentException("Parameters not valid.");
		this.parameters = parameters;
		initialize(CREATION_AS_OME_TIFF, parameters.getIcon());
		messageLabel.setText(getFileName());
		switch (parameters.getIndex()) {
			case ExportActivityParam.EXPORT_AS_OME_TIFF:
				type.setText(CREATION_AS_OME_TIFF);
				break;
		}
	}

	/**
	 * Creates a concrete loader.
	 * @see ActivityComponent#createLoader()
	 */
	protected UserNotifierLoader createLoader()
	{
		loader = new ExportLoader(viewer,  registry, parameters.getImage(), 
				new File(getFileName()), ExportLoader.EXPORT_AS_OME_TIFF, this);
		return loader;
	}

	/**
	 * Modifies the text of the component. 
	 * @see ActivityComponent#notifyActivityEnd()
	 */
	protected void notifyActivityEnd()
	{
		viewButton.setText(VIEW_TEXT);
		viewButton.setVisible(true);
		type.setText(DESCRIPTION_CREATED);
	}
	
	/**
	 * Modifies the text of the component. 
	 * @see ActivityComponent#notifyActivityCancelled()
	 */
	protected void notifyActivityCancelled()
	{
		type.setText(DESCRIPTION_CANCEL);
	}
	
	/** 
	 * No-operation in this case.
	 * @see ActivityComponent#notifyActivityError()
	 */
	protected void notifyActivityError() {}
	
}
