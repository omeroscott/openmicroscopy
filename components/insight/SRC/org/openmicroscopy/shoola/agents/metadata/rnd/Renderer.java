/*
 * org.openmicroscopy.shoola.agents.metadata.rnd.Renderer 
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
package org.openmicroscopy.shoola.agents.metadata.rnd;


//Java imports
import java.awt.Color;
import java.awt.Component;
import java.awt.Dimension;
import java.awt.Point;
import java.awt.image.BufferedImage;
import java.util.List;
import java.util.Map;
import javax.swing.JComponent;

//Third-party libraries
import com.sun.opengl.util.texture.TextureData;

//Application-internal dependencies
import omero.romio.PlaneDef;
import org.openmicroscopy.shoola.env.data.DSOutOfServiceException;
import org.openmicroscopy.shoola.env.rnd.RenderingControl;
import org.openmicroscopy.shoola.env.rnd.RenderingServiceException;
import org.openmicroscopy.shoola.env.rnd.RndProxyDef;
import org.openmicroscopy.shoola.util.ui.component.ObservableComponent;
import pojos.ChannelData;
import pojos.ImageData;
import pojos.PixelsData;

/** 
 * Defines the interface provided by the renderer component. 
 * The Renderer provides a top-level component hosting the rendering controls.
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
public interface Renderer
	extends ObservableComponent
{
	
	/** Identifies the <code>red</code> color band. */
	public static final int		RED_BAND = 0;
	
	/** Identifies the <code>green</code> color band. */
	public static final int		GREEN_BAND = 1;
	
	/** Identifies the <code>blue</code> color band. */
	public static final int		BLUE_BAND = 2;
	
	
    /** The value after which no ticks are displayed. */
	public static final int		MAX_NO_TICKS = 10;
    
	/** Identifies the grey scale color model. */
	public static final String  GREY_SCALE_MODEL = RenderingControl.GREY_SCALE;

	/** Identifies the RGB color model. */
	public static final String  RGB_MODEL = RenderingControl.RGB;
	
    /** 
     * The maximum number of channels before displaying the channels 
     * buttons slider.
     */
    public static final int		MAX_CHANNELS = RenderingControl.MAX_CHANNELS; 
    
    /** 
     * Bound property name indicating to render the plane with the 
     * new rendering settings. 
     */
    public final static String  RENDER_PLANE_PROPERTY = "renderPlane";
    
    /** Bound property name indicating that a new channel is selected. */
    public final static String  SELECTED_CHANNEL_PROPERTY = "selectedChannel";
    
    /** 
     * Bound property indicating that the pixels intensity interval is 
     * modified.
     */
    public final static String  INPUT_INTERVAL_PROPERTY = "inputInterval";
    
    /** Bound property indicating that the range to deal with has changed. */
    public final static String  RANGE_INPUT_PROPERTY = "rangeInput";
    
    /** Bound property indicating that the color model has changed. */
    public final static String  COLOR_MODEL_PROPERTY = "colorModel";
    
	/** Bound property name indicating that a new z-section is selected. */
	public final static String  Z_SELECTED_PROPERTY = "zSelected";

	/** Bound property name indicating that a new time-point is selected. */
	public final static String  T_SELECTED_PROPERTY = "tSelected";
	
	/** 
	 * Bound property name indicating to apply the rendering settings
	 * to all selected or displayed images. 
	 */
	public final static String  APPLY_TO_ALL_PROPERTY = "applyToAll";
	
	/** Bound property indicating that the color of a channel has changed. */
	public static final String	CHANNEL_COLOR_PROPERTY = "channelColor";
	
	/** Bound property indicating to reload the rendering engine. */
	public static final String	RELOAD_PROPERTY = "Reload";
	
	/** Bound property indicating to load the rendering settings. */
	public static final String	VIEWED_BY_PROPERTY = "ViewedBy";

	/** 
	 * Bound property indicating that the rendering settings have been 
	 * saved. 
	 */
	public static final String	SAVE_SETTINGS_PROPERTY = "saveSettings";
	
    /** 
     * Sets the pixels intensity interval for the
     * currently selected channel.
     * 
     * @param s The lower bound of the interval.
     * @param e The upper bound of the interval.
     */
    void setInputInterval(double s, double e);
    
    /** 
     * Sets the sub-interval of the device space. 
     * 
     * @param s         The lower bound of the interval.
     * @param e         The upper bound of the interval.
     */
    void setCodomainInterval(int s, int e);
    
    /**
     * Sets the bit resolution and updates the image.
     * 
     * @param v The new bit resolution.
     */
    void setBitResolution(int v);
    
    /**
     * Sets the selected channel. This method is invoked when 
     * the channel has been selected from the viewer.
     * 
     * @param index The index of the selected channel.
     */
    void setSelectedChannel(int index);
    
    /**
     * Sets the family and updates the image.
     * 
     * @param family The new family value.
     */
    void setFamily(String family);
    
    /**
     * Sets the coefficient identifying a curve in the family
     * and updates the image.
     * 
     * @param k The new curve coefficient.
     */
    void setCurveCoefficient(double k);
    
    /**
     * Sets the noise reduction flag to select the mapping algorithm
     * and updates the image.
     * 
     * @param b The noise reduction flag.
     */
    void setNoiseReduction(boolean b);
    
    /**
     * Returns the <code>Codomain map context</code> corresponding to
     * the specifed class.
     * 
     * @param mapType       The class identifying the context.
     * @return See above.
     */
    //CodomainMapContext getCodomainMapContext(Class mapType);

    /**
     * Fired if the color model has been changed from RGB -> Greyscale or 
     * vice versa.
     */
    void setColorModelChanged();
    
    /**
     * Returns the current state.
     * 
     * @return See above
     */
    public int getState();
    
    /** Closes and disposes. */
    public void discard();

    /**
     * Returns the lower bound of the pixels intensity interval for the
     * currently selected channel.
     * 
     * @return See above.
     */
    public double getWindowStart();
    
    /**
     * Returns the upper bound of the pixels intensity interval for the
     * currently selected channel.
     * 
     * @return See above.
     */
    public double getWindowEnd();
    
    /**
     * Returns the global minimum for the currently selected channel.
     * 
     * @return See above.
     */
    public double getGlobalMin();
    
    /**
     * Returns the global maximum for the currently selected channel.
     * 
     * @return See above.
     */
    public double getGlobalMax();
    
    /**
     * Returns the global minimum for the currently selected channel.
     * 
     * @return See above.
     */
    public double getLowestValue();
    
    /**
     * Returns the global maximum for the currently selected channel.
     * 
     * @return See above.
     */
    public double getHighestValue();

    /**
     * Returns the {@link RendererUI View}.
     * 
     * @return See above.
     */
    public JComponent getUI();
	
	/**
	 * Invokes when the state of the viewer has changed.
	 * 
	 * @param b Pass <code>true</code> to enable the UI components, 
	 *          <code>false</code> otherwise.
	 */
	public void onStateChange(boolean b);

	/**
	 * Indicates that a channel has been selected using the channel button.
	 * 
	 * @param index	 The index of the channel.
	 * @param active Pass <code>true</code> to indicate that the channel is
	 * 				 active, <code>false</code> otherwise.
	 */
	void setChannelSelection(int index, boolean active);

	/**
	 * Sets the color of the specified channel depending on the current color
	 * model.
	 * 
	 * @param index The index of the channel.
	 * @param color The color to set.
	 */
	void setChannelColor(int index, Color color);

	/**
	 * Sets the color model.
	 * 
	 * @param index 	One of the constants defined by this class.
	 * @param update	Flag indicating to fire a property change 
	 * 					indicating to update the image.
	 */
	void setColorModel(String index, boolean update);

	/**
	 * Returns the color model.
	 * 
	 * @return See above.
	 */
	String getColorModel();
	
	/**
	 * Sets the selected XY-plane. A new plane is then rendered.
	 * 
	 * @param z The selected z-section.
	 * @param t The selected timepoint.
	 * @param bin The selected bin, only used for lifetime.
	 */
	void setSelectedXYPlane(int z, int t, int bin);

	/** Applies the rendering settings to the selected or displayed images. */
	void applyToAll();
	
	/** 
	 * Notifies that the rendering settings have been applied. 
	 * 
	 * @param rndControl The rendering control to reset.
	 */
	void onSettingsApplied(RenderingControl rndControl);
	
	/**
	 * Returns the sizeX.
	 * 
	 * @return See above.
	 */
	int getPixelsDimensionsX();

	/**
	 * Returns the sizeY.
	 * 
	 * @return See above.
	 */
	int getPixelsDimensionsY();

	/**
	 * Returns the maximum number of z-sections.
	 * 
	 * @return See above.
	 */
	int getPixelsDimensionsZ();

	/**
	 * Returns the maximum number of timepoints.
	 * 
	 * @return See above.
	 */
	int getPixelsDimensionsT();
	
	/**
	 * Returns the number of channels.
	 * 
	 * @return See above.
	 */
	int getPixelsDimensionsC();

	/**
	 * Returns the currently selected z-section.
	 * 
	 * @return See above.
	 */
	int getDefaultZ();

	/**
	 * Returns the currently selected timepoint.
	 * 
	 * @return See above.
	 */
	int getDefaultT();
	
	/**
	 * Returns a sorted unmodifiable list of {@link ChannelData}s.
	 * 
	 * @return See above
	 */
	List<ChannelData> getChannelData();
	
	/**
	 * Returns the color associated to a channel.
	 * 
	 * @param index The index of the channel.
	 * @return See above.
	 */
	Color getChannelColor(int index);
	
	/**
	 * Returns <code>true</code> if the channel is mapped, <code>false</code>
	 * otherwise.
	 * 
	 * @param w	The channel's index.
	 * @return See above.
	 */
	boolean isChannelActive(int w);
	
	/**
	 * Returns a list of active channels.
	 * 
	 * @return See above.
	 */
	List<Integer> getActiveChannels();
	
	/**
	 * Returns the size in microns of a pixel along the X-axis.
	 * 
	 * @return See above.
	 */
	double getPixelsSizeX();
	/**
	 * Returns the size in microns of a pixel along the Y-axis.
	 * 
	 * @return See above.
	 */
	double getPixelsSizeY();
	/**
	 * Returns the size in microns of a pixel along the Y-axis.
	 * 
	 * @return See above.
	 */
	double getPixelsSizeZ();
	
	/**
	 * Returns a 3-dimensional array of boolean value, one per color band.
	 * The first (resp. second, third) element is set to <code>true</code> 
	 * if an active channel is mapped to <code>RED</code> (resp. 
	 * <code>GREEN</code>, <code>BLUE</code>), to <code>false</code> otherwise.
	 * 
	 * @return See above
	 */
	boolean[] hasRGB();

	/**
	 * Returns <code>true</code> if the channel is mapped
	 * to <code>Red</code> if the band is {@link #RED_BAND}, 
	 * to <code>Green</code> if the band is {@link #GREEN_BAND},
	 * to <code>Blue</code> if the band is {@link #BLUE_BAND},
	 * <code>false</code> otherwise.
	 * 
	 * @param band  The color band.
	 * @param index The index of the channel.
	 * @return See above.
	 */
	boolean isColorComponent(int band, int index);

	/**
	 * Returns a copy of the current rendering settings.
	 * 
	 * @return See above.
	 */
	RndProxyDef getRndSettingsCopy();

	/**
	 * Resets the rendering settings.
	 * 
	 * @param settings  The settings to reset.
	 * @param update    Pass <code>true</code> to update the image,
	 * 					<code>false</code> otherwise.
	 */
	void resetSettings(RndProxyDef settings, boolean update);

	/** Resets the default settings. */
	void resetSettings();

	/** Sets the original default settings. */
	void setOriginalRndSettings();

	/**
	 * Returns <code>true</code> if the passed set of pixels is compatible
	 * with the pixels set currently rendered.
	 * 
	 * @param pixels The pixels set to check.
	 * @return See above.
	 */
	boolean validatePixels(PixelsData pixels);

	/**
	 * Returns <code>true</code> if the image is compressed, 
	 * <code>false</code> otherwise.
	 * 
	 * @return See above.
	 */
	boolean isCompressed();
	
	/** 
	 * Saves the rendering settings and returns the saved object.
	 * 
	 * @return See above
	 * @throws RenderingServiceException 	If an error occurred while setting 
     * 										the value.
     * @throws DSOutOfServiceException  	If the connection is broken. 
	 */
	RndProxyDef saveCurrentSettings()
		throws RenderingServiceException, DSOutOfServiceException;

	/** Fires a property to indicate to save the settings. */
	void saveSettings();
	
	/**
	 * Sets the compression level.
	 * 
	 * @param compressionLevel 	One of the compression level defined by 
	 * 							{@link RenderingControl} I/F.
	 */
	void setCompression(int compressionLevel);

	/**
	 * Returns the compression level.
	 * 
	 * @return See above.
	 */
	int getCompressionLevel();

	/**
	 * Returns <code>true</code> if the passed rendering settings are the same
	 * that the current one, <code>false</code> otherwise.
	 * 
	 * @param def 		 The settings to check.
	 * @param checkPlane Pass <code>true</code> to take into account the 
	 * 					 z-section and time-point, <code>false</code> 
	 * 					 otherwise.
	 * @return See above.
	 */
	boolean isSameSettings(RndProxyDef def, boolean checkPlane);

	/**
	 * Turns on or off the specified channel.
	 * 
	 * @param index  The index of the channel
	 * @param active Pass <code>true</code> to turn the channel on, 
	 * 				 <code>false</code> to turn it off.
	 */
	void setActive(int index, boolean active);

	/**
	 * Sets the interval of the pixels intensity values to map.
	 * 
	 * @param index The index of the channel
	 * @param start The lower bound of the interval.
	 * @param end	The upper bound of the interval.
	 */
	void setChannelWindow(int index, double start, double end);
	
	/**
	 * Renders the specified plane.
	 * 
	 * @param pDef The plane to render.
	 * @return See above.
	 */
	BufferedImage renderPlane(PlaneDef pDef);
	
	/** 
	 * Sets the maximum range for channels.
	 * 
	 *  @param absolute Pass <code>true</code> to set it to the absolute value,
	 *  				<code>false</code> to the minimum and maximum.
	 */
	void setRangeAllChannels(boolean absolute);
	
	/**
	 * Renders the specified plane.
	 * 
	 * @param pDef The plane to render.
	 * @return See above.
	 */
	TextureData renderPlaneAsTexture(PlaneDef pDef);
	
    /**
     * Returns <code>true</code> if the passed channels compose an RGB image, 
     * <code>false</code> otherwise.
     * 
     * @param channels The collection of channels to handle.
     * @return See above.
     */
	boolean isMappedImageRGB(List channels);

	/**
	 * Creates an image with only the passed channel turned on.
	 * All active channels will turn off then back on when the has been created.
	 * 
	 * @param color		Pass <code>true</code> for a color image,
	 * 					<code>false</code> for a greyscale image.
	 * @param channel 	The channel to handle.
	 * @param pDef 		The plane to render.
	 * @return See above.
	 */
	BufferedImage createSingleChannelImage(boolean color, int channel, 
			PlaneDef pDef);
	
    /**
     * Sets the overlays.
     * 
     * @param tableID  The id of the table.
     * @param overlays The overlays to set, or <code>null</code> to turn 
     * the overlays off.
     */
    public void setOverlays(long tableID, Map<Long, Integer> overlays); 
    
    /** Refreshes the renderer view. */
    public void refresh();
    
    /** 
     * Renders and displays the rendered image in the preview. 
     * Invokes only when the renderer is used for general purpose.
     */
    public void renderPreview();
    
    /**
     * Returns the image or <code>null</code>.
     * 
     * @return See above.
     */
    ImageData getRefImage();
    
    /**
     * Returns the initial rendering settings.
     * 
     * @return See above.
     */
	RndProxyDef getInitialRndSettings();
	
	/** 
	 * Retrieves the rendering settings set by other users. 
	 * 
	 * @param source	The component that requested the pop-up menu.
	 * @param location	The point at which to display the menu, relative to the
	 *                  <code>component</code>'s coordinates.
	 */
	void retrieveRelatedSettings(Component source, Point location);
	
	/** 
	 * Indicates that the rendering settings are being loaded if 
	 * the passed value is <code>true</code>, loaded if <code>false</code>.
	 * 
	 * @param loading Pass <code>true</code> to indicate that the settings are 
	 * 				  being loaded, <code>false</code> when loaded.
	 * @param list    The list of objects displaying the rendering settings 
	 * 				  and the associated images.
	 */
	void loadRndSettings(boolean loading, List results);
	
	/**
	 * Returns the size of a tile.
	 * 
	 * @return See above.
	 */
	Dimension getTileSize();
	
	/**
	 * Returns the possible resolution levels. This method should only be used
	 * when dealing with large images.
	 * 
	 * @return See above.
	 */
	int getResolutionLevels();
	
	/**
	 * Returns the currently selected resolution level. This method should only 
	 * be used when dealing with large images.
	 * 
	 * @return See above.
	 */
	int getSelectedResolutionLevel();
	
	/**
	 * Sets resolution level. This method should only be used when dealing with
	 * large images.
	 * 
	 * @param level The value to set.
	 */
	void setSelectedResolutionLevel(int level);
	
	/**
	 * Returns <code>true</code> if it is a large image, 
	 * <code>false</code> otherwise.
	 * 
	 * @return See above.
	 */
	boolean isBigImage();
	
}
