/*
 * org.openmicroscopy.shoola.env.ui.DownloadAndZipActivity 
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
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

//Third-party libraries

//Application-internal dependencies
import org.openmicroscopy.shoola.env.config.Registry;
import org.openmicroscopy.shoola.env.data.model.DownloadAndZipParam;
import org.openmicroscopy.shoola.util.file.IOUtil;
import pojos.FileAnnotationData;

/** 
 * Downloads the files and creates a zip.
 *
 * @author Jean-Marie Burel &nbsp;&nbsp;&nbsp;&nbsp;
 * <a href="mailto:j.burel@dundee.ac.uk">j.burel@dundee.ac.uk</a>
 * @author Donald MacDonald &nbsp;&nbsp;&nbsp;&nbsp;
 * <a href="mailto:donald@lifesci.dundee.ac.uk">donald@lifesci.dundee.ac.uk</a>
 * @version 3.0
 * <small>
 * (<b>Internal version:</b> $Revision: $Date: $)
 * </small>
 * @since 3.0-Beta4
 */
public class DownloadAndZipActivity 
	extends ActivityComponent
{

	/** The description of the activity when cancelled. */
	private static final String		DESCRIPTION_CANCEL = "Download cancelled";
	
	/** The description of the activity when finished. */
	private static final String		DESCRIPTION = "Zip created";
	
	/** The parameters hosting information about the file to download. */
    private DownloadAndZipParam parameters;
    
    /** The name of the zip file. */
    private File zipFolder;
    
	/**
	 * Creates a new instance.
	 * 
	 * @param viewer
	 * @param registry
	 * @param parameters
	 */
	public DownloadAndZipActivity(UserNotifier viewer, Registry registry,
    		DownloadAndZipParam parameters)
	{
		super(viewer, registry);
		if (parameters == null)
			throw new IllegalArgumentException("No parameters");
		this.parameters = parameters;
		initialize("Download", parameters.getIcon());
		File folder = parameters.getFolder();
		if (!folder.exists()) {
			folder.mkdir();
			zipFolder = folder;
		} else if (folder.isFile()) {
			File parent = folder.getParentFile();
			File f = new File(parent, folder.getName()+"_zip");
			if (f.mkdir())
				zipFolder = f;
		}
	}
	
	/**
	 * Creates a concrete loader.
	 * @see ActivityComponent#createLoader()
	 */
	protected UserNotifierLoader createLoader()
	{
		List<FileAnnotationData> files = parameters.getFiles();
		Iterator<FileAnnotationData> i = files.iterator();
		Map<FileAnnotationData, File> toLoad = 
			new HashMap<FileAnnotationData, File>();
		FileAnnotationData fa;
		
		while (i.hasNext()) {
			fa = i.next();
			toLoad.put(fa, new File(zipFolder, fa.getFileName()));
		}
		loader = new FilesLoader(viewer, registry, toLoad, this);
		return loader;
	}

	/**
	 * Modifies the text of the component. 
	 * @see ActivityComponent#notifyActivityEnd()
	 */
	protected void notifyActivityEnd()
	{
		resultButton.setVisible(false);
		try {
			IOUtil.zipDirectory(zipFolder);
			messageLabel.setText(zipFolder.getAbsolutePath());
			//empty folder.
			File[] entries = zipFolder.listFiles();
			for (int i = 0; i < entries.length; i++) {
				entries[i].delete();
			}
			zipFolder.delete();
		} catch (Exception e) {
			//Notify user
		}
		type.setText(DESCRIPTION); 
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
