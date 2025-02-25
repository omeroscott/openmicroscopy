/*
 * org.openmicroscopy.shoola.env.data.views.calls.FileUploader
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
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *  
 *  You should have received a copy of the GNU General Public License along
 *  with this program; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 *------------------------------------------------------------------------------
 */
package org.openmicroscopy.shoola.env.data.views.calls;

//Java imports
import java.io.File;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

//Third-party libraries

//Application-internal dependencies
import org.openmicroscopy.shoola.env.LookupNames;
import org.openmicroscopy.shoola.env.data.views.BatchCall;
import org.openmicroscopy.shoola.env.data.views.BatchCallTree;
import org.openmicroscopy.shoola.svc.SvcRegistry;
import org.openmicroscopy.shoola.svc.communicator.Communicator;
import org.openmicroscopy.shoola.svc.communicator.CommunicatorDescriptor;
import org.openmicroscopy.shoola.svc.transport.HttpChannel;
import org.openmicroscopy.shoola.util.file.ImportErrorObject;
import org.openmicroscopy.shoola.util.ui.FileTableNode;
import org.openmicroscopy.shoola.util.ui.MessengerDetails;

/**
 * Uploads files to the QA system.
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
public class FileUploader
	extends BatchCallTree
{

	/** 
	 * Object containing information about the files to upload to the server.
	 */
	private MessengerDetails	details;
	
	/** Partial result. Returns the uploaded file. */
	private Object uploadedFile;
	
	/**
	 * Uploads the specified files to the server.
	 * 
	 * @param object The object hosting the files to be uploaded.
	 */
	private void uploadFile(ImportErrorObject object)
	{
		String tokenURL = (String) context.lookup(LookupNames.TOKEN_URL);
		String processURL = 
			(String) context.lookup(LookupNames.PROCESSING_URL);
		String appName = 
			(String) context.lookup(LookupNames.APPLICATION_NAME_BUG);
		int timeout = (Integer) context.lookup(LookupNames.POST_TIMEOUT);
		Object version = context.lookup(LookupNames.VERSION);
		String v = "";
    	if (version != null && version instanceof String)
    		v = (String) version;

		try {
			Communicator c; 
			CommunicatorDescriptor desc = new CommunicatorDescriptor
				(HttpChannel.CONNECTION_PER_REQUEST, tokenURL, -1);
			c = SvcRegistry.getCommunicator(desc);
			StringBuilder token = new StringBuilder();

			if (details.isExceptionOnly()) {
				c.submitError("",
						details.getEmail(), details.getComment(), 
						details.getExtra(), object.getException().toString(), 
						appName, v, token);
			} else {
				String[] usedFiles = object.getUsedFiles();
				List<File> additionalFiles = null;
				if (usedFiles != null && usedFiles.length > 0) {
					additionalFiles = new ArrayList<File>();
					for (int i = 0; i < usedFiles.length; i++) {
						additionalFiles.add(new File(usedFiles[i]));
					}
				}
				c.submitFilesError("",
						details.getEmail(), details.getComment(), 
						details.getExtra(), object.getException().toString(), 
						appName, v, object.getFile(), additionalFiles, token);
				desc = new CommunicatorDescriptor(
						HttpChannel.CONNECTION_PER_REQUEST, processURL, 
						timeout);
				c = SvcRegistry.getCommunicator(desc);
				StringBuilder reply = new StringBuilder();
				String reader = object.getReaderType();
				if (object.getFile() != null)
					c.submitFile(token.toString(), object.getFile(), reader, reply);
				if (additionalFiles != null) {
					Iterator<File> i = additionalFiles.iterator();
					while (i.hasNext()) {
						c.submitFile(token.toString(), i.next(), reader, reply);
					}
				}
			}
			
			uploadedFile = object;
		} catch (Exception e) {
		}
	}
	
    /**
     * Returns the lastly uploaded file.
     * This will be packed by the framework into a feedback event and
     * sent to the provided call observer, if any.
     * 
     * @return See above.
     */
    protected Object getPartialResult() { return uploadedFile; }
    
    /**
     * Returns <code>null</code> as there's no final result.
     * In fact, uploaded files are progressively delivered with 
     * feedback events. 
     * @see BatchCallTree#getResult()
     */
    protected Object getResult() { return null; }
    
	/**
     * Adds a {@link BatchCall} to the tree for each file to upload to the
     * server.
     * @see BatchCallTree#buildTree()
     */
    protected void buildTree()
    {
    	List l = (List) details.getObjectToSubmit();
    	String description = "Uploading files to QA system.";
		Iterator i = l.iterator();
		FileTableNode node;
		while (i.hasNext()) {
			node = (FileTableNode) i.next();
			node.setStatus(true);
			final ImportErrorObject f = node.getFailure();
			add(new BatchCall(description) {
        		public void doCall() { uploadFile(f); }
        	}); 
		}
    }
    
    /**
     * Creates a new instance.
     * 
     * @param details 	Object information about the files to upload to the 
     * 					server.
     */
    public FileUploader(MessengerDetails details)
    {
    	if (details == null)
    		throw new IllegalArgumentException("No files to submit.");
    	this.details = details;
    }
    
}
