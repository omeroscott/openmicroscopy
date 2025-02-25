/*
 * org.openmicroscopy.shoola.agents.imviewer.browser.BrowserUI
 *
 *------------------------------------------------------------------------------
 *  Copyright (C) 2006 University of Dundee. All rights reserved.
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

package org.openmicroscopy.shoola.agents.imviewer.browser;


//Java imports
import java.awt.Component;
import java.awt.Dimension;
import java.awt.Point;
import java.awt.Rectangle;
import java.awt.event.AdjustmentEvent;
import java.awt.event.AdjustmentListener;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.awt.event.MouseListener;
import java.awt.image.BufferedImage;
import java.beans.PropertyChangeEvent;
import java.beans.PropertyChangeListener;
import java.util.HashMap;
import java.util.Map;
import javax.swing.JComponent;
import javax.swing.JFrame;
import javax.swing.JLayeredPane;
import javax.swing.JPanel;
import javax.swing.JScrollBar;
import javax.swing.JScrollPane;
import javax.swing.JViewport;
import javax.swing.SwingUtilities;

//Third-party libraries
import com.sun.opengl.util.texture.TextureData;


//Application-internal dependencies
import org.openmicroscopy.shoola.agents.imviewer.ImViewerAgent;

/** 
 * Hosts the UI components displaying the rendered image.
 * Note that the layout manager of the viewport is set to <code>null</code>.
 *
 * @author  Jean-Marie Burel &nbsp;&nbsp;&nbsp;&nbsp;
 * 				<a href="mailto:j.burel@dundee.ac.uk">j.burel@dundee.ac.uk</a>
 * @author	Andrea Falconi &nbsp;&nbsp;&nbsp;&nbsp;
 * 				<a href="mailto:a.falconi@dundee.ac.uk">a.falconi@dundee.ac.uk</a>
 * @author	Donald MacDonald &nbsp;&nbsp;&nbsp;&nbsp;
 * 				<a href="mailto:donald@lifesci.dundee.ac.uk">donald@lifesci.dundee.ac.uk</a>
 * @version 3.0
 * <small>
 * (<b>Internal version:</b> $Revision: $ $Date: $)
 * </small>
 * @since OME2.2
 */
class BrowserUI
    extends JScrollPane
    implements AdjustmentListener
{

    /**
     * The Layered pane hosting the {@link BrowserCanvas} and any other 
     * UI components added on top of it.
     */
    private JLayeredPane        	layeredPane;

    /** The canvas hosting the image. */
    private JComponent  			canvas;
    
    /** Reference to the Model. */
    private BrowserModel        	model;
    
    /** Reference to the Control. */
    private BrowserControl      	controller;
    
    /** Listens to the mouse moves on the Image canvas. */
    private ImageCanvasListener		canvasListener;
    
    /** Components related to the view while settings the bounds. */
    private Map<Integer, JComponent> siblings;

    /** Flag indicating if the experimenter uses the scrollbars. */
    private boolean					adjusting;

    /** The bird eye view.*/
    private BirdEyeViewComponent	birdEyeView;
    
    private JPanel glass;
    
    /** Sets the location of the bird eye view.*/
    private void setBirdEyeViewLocation()
    {
    	if (birdEyeView == null) return;
		Rectangle r = getViewport().getViewRect();
		Point p = new Point(0, 0);
		p = SwingUtilities.convertPoint(getViewport(), p, glass);
		birdEyeView.setLocation(p);
		switch (birdEyeView.getLocationIndex()) {
			case ImageCanvas.BOTTOM_RIGHT:
				Dimension d = birdEyeView.getSize();
				p = new Point(p.x+r.width-d.width, 
						p.y+r.height-d.height);
				birdEyeView.setLocation(p);
				break;
			case ImageCanvas.TOP_LEFT:
			default:
				birdEyeView.setLocation(p);
		}
    }
    
    /** 
     * Displays the region of the image selected using the bird eye view.
     * 
     * @param region See above.
     */
    private void displaySelectedRegion(Rectangle region)
    {
    	if (region == null) return;
    	Dimension d = birdEyeView.getSize();
    	Rectangle rl = canvas.getBounds();
    	int sizeX = rl.width;//model.getMaxX()/2;
    	int sizeY = rl.height;//model.getMaxY()/2;
    	double vx = sizeX/d.width;
    	double vy = sizeY/d.height;
    	int x = (int) (vx*region.x);
    	int y = (int) (vy*region.y);
    	int w = (int) (vx*region.width);
    	int h = (int) (vy*region.height);
    	Rectangle r = new Rectangle(x, y, w, h);
    	model.checkTilesToLoad(r);
    	//scrollTo(r, false);		
    	getViewport().setViewPosition(new Point(r.x, r.y));
    	setBirdEyeViewLocation();
    }
    
    /** Sets the location of the region.*/
    private void setSelectionRegion()
    {
    	if (birdEyeView == null) return;
    	Dimension d = birdEyeView.getSize();
    	if (d.width == 0 || d.height == 0) return;
    	Rectangle r = getViewport().getViewRect();
    	Rectangle rl = canvas.getBounds();
    	int sizeX = rl.width;// model.getMaxX();
    	int sizeY = rl.height;//model.getMaxY();
    	int rx = sizeX/d.width;
    	int ry = sizeY/d.height;
    	if (rx == 0) rx = 1;
    	if (ry == 0) ry = 1;
    	int x = (int) (r.x/rx);
    	int y = (int) (r.y/ry);
    	int w = (int) (r.width/rx);
    	int h = (int) (r.height/ry);
    	birdEyeView.setSelection(x, y, w, h);
    }
    
	/** Centers the image.*/
	private void center()
	{
		Rectangle r = getViewport().getViewRect();
		Dimension d = layeredPane.getPreferredSize();
		int xLoc = ((r.width-d.width)/2);
		int yLoc = ((r.height-d.height)/2);
		JScrollBar hBar = getHorizontalScrollBar();
		JScrollBar vBar = getVerticalScrollBar();
		if (hBar.isVisible()) xLoc = layeredPane.getX();
		if (vBar.isVisible()) yLoc = layeredPane.getY();
		JComponent sibling = siblings.get(model.getSelectedIndex());
		if (sibling != null) 
			sibling.setBounds(sibling.getBounds());
		layeredPane.setBounds(xLoc, yLoc, d.width, d.height);
		setSelectionRegion();
		setBirdEyeViewLocation();
	}
	
    /** Initializes the components composing the display. */
    private void initComponents()
    {
        layeredPane = new JLayeredPane();
        if (ImViewerAgent.hasOpenGLSupport()) {
        	canvas = new BrowserCanvas(model, this);
        } else {
        	 canvas = new BrowserBICanvas(model, this);
        }
       
        //The image canvas is always at the bottom of the pile.
        layeredPane.add(canvas, Integer.valueOf(0));
       
        canvasListener = new ImageCanvasListener(this, model, canvas);
        canvasListener.setHandleKeyDown(true);
        MouseAdapter adapter = new MouseAdapter() {
        	
        	/**
        	 * Removes the adjustment listener to the scroll bars.
        	 * @see MouseListener#mouseReleased(MouseEvent)
        	 */
        	public void mouseReleased(MouseEvent e) {
				 installScrollbarListener(false);
			}
        	
        	/**
        	 * Attaches an adjustment listener to the scroll bars.
        	 * @see MouseListener#mousePressed(MouseEvent)
        	 */
        	public void mousePressed(MouseEvent e) {
				installScrollbarListener(true);
				
			}
		};
        getVerticalScrollBar().addMouseListener(adapter);
        getHorizontalScrollBar().addMouseListener(adapter);
    }
    
    /** Builds and lays out the GUI. */
    private void buildGUI()
    {
    	JViewport viewport = getViewport();
    	viewport.setLayout(null);
    	viewport.setBackground(model.getBackgroundColor());
    	viewport.add(layeredPane);
    }
    
	/**
	 * Returns <code>true</code> if the scrollbars are visible,
	 * <code>false</code> otherwise.
	 * 
	 * @return See above.
	 */
	private boolean scrollbarsVisible()
	{
		JScrollBar hBar = getHorizontalScrollBar();
		JScrollBar vBar = getVerticalScrollBar();
		if (hBar.isVisible()) return true;
		if (vBar.isVisible()) return true;
		return false;
	}
	
    /** Creates a new instance. */
    BrowserUI()
    {
    	siblings = new HashMap<Integer, JComponent>();
    }
    
    /**
     * Links this View to its Controller and Model
     * 
     * @param controller    Reference to the Control.
     *                      Mustn't be <code>null</code>.
     * @param model         Reference to the Model.
     *                      Mustn't be <code>null</code>.
     */
    void initialize(BrowserControl controller, BrowserModel model)
    {
        if (model == null) throw new NullPointerException("No model.");
        if (controller == null) throw new NullPointerException("No control.");
        this.model = model;
        this.controller = controller;
        initComponents();
        buildGUI();
    }

	/** Creates the image to save. */
	BufferedImage activeFileSave()
	{
		if (canvas instanceof BrowserCanvas) {
			BrowserCanvas bc = (BrowserCanvas) canvas;
			bc.activeSave();
			canvas.repaint();
			return bc.getImageToSave();
		}
		return null;
	}
	
    /** 
     * Sets the component related to this component when the bounds of 
     * the view are reset.
     * 
     * @param index 	The index corresponding to the passed component. 
     * @param sibling 	The value to set.
     */
    void setSibling(int index, JComponent sibling)
    { 
    	siblings.put(index, sibling);
    }
    
    /**
     * Adds the component to the {@link #layeredPane}. The component will
     * be added to the top of the pile
     * 
     * @param c The component to add.
     * @param reset Pass <code>true</code> to re-organize the components, 
     * 				<code>false</code> otherwise.
     */
    void addComponentToLayer(Component c, boolean reset)
    {
    	Component[] components = layeredPane.getComponents();
    	int count = components.hashCode();
    	for (int i = 0; i < components.length; i++) {
			if (components[i] == c) return;
		}
    	
    	if (reset) {
    		for (int i = 0; i < components.length; i++) {
    			if (components[i] != canvas)
    				layeredPane.remove(components[i]);
			}
    		layeredPane.add(c, Integer.valueOf(1));
    		for (int i = 0; i < components.length; i++) {
    			if (components[i] != canvas)
    				layeredPane.add(components[i], Integer.valueOf(1));
    		}
    	} else layeredPane.add(c, Integer.valueOf(1));
    	
    }
    
    /**
     * Initializes or recycles the bird eye view and add it to the
     * display.
     * 
     * @param image The image to display
     */
    void setBirdEyeView(BufferedImage image)
	{
    	if (birdEyeView == null) {
    		birdEyeView = new BirdEyeViewComponent(
    				ImageCanvas.BOTTOM_RIGHT);
    		birdEyeView.addPropertyChangeListener(new PropertyChangeListener() {
				
    			/**
    			 * Listen to the property indicating to display a new location.
    			 * @see PropertyChangeListener#propertyChange(PropertyChangeEvent)
    			 */
				public void propertyChange(PropertyChangeEvent evt)
				{
					String name = evt.getPropertyName();
					if (BirdEyeViewComponent.DISPLAY_REGION_PROPERTY.equals(
							name)) {
						displaySelectedRegion((Rectangle) evt.getNewValue());
					} else if (
							BirdEyeViewComponent.FULL_DISPLAY_PROPERTY.equals(
							name)) {
						setBirdEyeViewLocation();
					}
				}
			});
    		birdEyeView.setup();
    		JFrame frame = model.getParentModel().getUI();
    		glass = (JPanel) frame.getGlassPane();
    		glass.setLayout(null);
    		glass.add(birdEyeView);
    		glass.setVisible(true);
    		
    		//addComponentToLayer(birdEyeView, false);
    		setBirdEyeViewLocation();
    	}
    	Dimension d = birdEyeView.getSize();
    	birdEyeView.setImage(image);
    	if (d.width == 0 || d.height == 0)
    		setSelectionRegion();
	}
    
    /**
     * Removes the component from the {@link #layeredPane}.
     * 
     * @param c 	The component to remove.
     */
    void removeComponentFromLayer(JComponent c)
    {
    	layeredPane.remove(c);
    }

    /**
     * Creates the displayed image and paints it.
     * This method should be called straight after setting the 
     * rendered image.
     */
    void paintMainImage()
    {
    	if (canvas instanceof BrowserCanvas) {
    		TextureData img = model.getRenderedImageAsTexture();
        	if (img == null) return;
        	double zoom = model.getZoomFactor();
        	int w = (int) (img.getWidth()*zoom);
        	int h = (int) (img.getHeight()*zoom);
        	canvasListener.setAreaSize(w, h);
        	canvas.repaint();
    	} else {
    		if (model.getRenderedImage() == null) return;
    		model.createDisplayedImage();
    		BufferedImage img = model.getDisplayedImage();
    		if (img == null) return;
    		canvasListener.setAreaSize(img.getWidth(), img.getHeight());
    		canvas.repaint();
    	}
    }
    
    /** Displays the zoomed image. */
    void zoomImage()
    {
    	adjusting = false;
    	if (canvas instanceof BrowserCanvas) {
    		TextureData img = model.getRenderedImageAsTexture();
        	if (img == null) return;
        	double zoom = model.getZoomFactor();
        	int w = (int) (img.getWidth()*zoom);
        	int h = (int) (img.getHeight()*zoom);
        	setComponentsSize(w, h);
        	canvasListener.setAreaSize(img.getWidth(), img.getHeight());
        	
    	} else {
    		if (model.getRenderedImage() == null) return;
    		model.createDisplayedImage();
    		BufferedImage img = model.getDisplayedImage();
    		if (img == null) return;
    		setComponentsSize(img.getWidth(), img.getHeight());
    		canvasListener.setAreaSize(img.getWidth(), img.getHeight());
    		getViewport().setViewPosition(new Point(-1, -1));
    		canvas.repaint();
    		setBounds(getBounds());
    	}
    	getViewport().setViewPosition(new Point(-1, -1));
    	canvas.repaint();
    	setBounds(getBounds());
    }
      
    /**
     * Sets the size of the components because a layeredPane doesn't have a 
     * layout manager.
     * 
     * @param w The width to set.
     * @param h The height to set.
     */
    void setComponentsSize(int w, int h)
    {
    	Dimension d = new Dimension(w, h);
    	layeredPane.setPreferredSize(d);
        layeredPane.setSize(d);
        canvas.setPreferredSize(d);
        canvas.setSize(d);
        if (model.isBigImage()) {
        	setSelectionRegion();
        	Rectangle r = getViewport().getViewRect();
    		d = layeredPane.getPreferredSize();
			if (d.width < r.width && d.height < r.height) {
				center();
			}
        }
    }
    
    /** 
     * Returns the current size of the viewport. 
     * 
     * @return see above. 
     */
    Dimension getViewportSize() { return getViewport().getSize(); }

    /**
     * Installs or removes listener to (resp. from) scroll bars.
     * 
     * @param add	Passes <code>true</code> to install,
     * 				<code>false</code> to remove.
     */
    private void installScrollbarListener(boolean add)
    {
    	if (add) {
    		getHorizontalScrollBar().addAdjustmentListener(this);
    		getVerticalScrollBar().addAdjustmentListener(this);
    	} else {
    		getHorizontalScrollBar().removeAdjustmentListener(this);
    		getVerticalScrollBar().removeAdjustmentListener(this);
    	}
    }
    
    /**
     * Pans to the new location.
     * 
     * @param x The X-coordinate of the mouse dragged minus mouse pressed.
     * @param y The Y-coordinate of the mouse dragged minus mouse pressed.
     * @param load Passed <code>true</code>
     */
    void pan(int x, int y, boolean load)
    {
    	Rectangle r = getViewport().getViewRect();
    	int vx = r.x;
    	int vy = r.y;
    	if (x < 0) vx += -x;
    	if (x > 0) vx -= x;
    	if (y < 0) vy += -y;
    	if (y > 0) vy -= y;
    	getViewport().setViewPosition(new Point(vx, vy));
    	setSelectionRegion();
    	setBirdEyeViewLocation();
    	if (load)
    		model.checkTilesToLoad(getViewport().getViewRect());
    }
    
	/**
	 * Scrolls to the location.
	 * 
	 * @param bounds 			The bounds of the node.
	 * @param blockIncrement	Pass <code>true</code> to consider block
	 * 							increment, <code>false</code> otherwise.
	 * 						
	 */
	void scrollTo(Rectangle bounds, boolean blockIncrement)
	{
		//installScrollbarListener(false);
		Rectangle viewRect = getViewport().getViewRect();
		JScrollBar hBar = getHorizontalScrollBar();
		JScrollBar vBar = getVerticalScrollBar();
		int x = 0;
		int y = 0;
		if (!viewRect.contains(bounds)) {
			int deltaX = viewRect.x-bounds.x;
			int deltaY = viewRect.y-bounds.y;
			if (deltaX < 0 && blockIncrement)
				x = hBar.getValue()+hBar.getBlockIncrement();
			else {
				int w = viewRect.width-bounds.width;
				if (w < 0) w = -w;
				x = bounds.x-w/2;
			}
			if (deltaY < 0 && blockIncrement)
				y = vBar.getValue()+vBar.getBlockIncrement();
			else {
				int h = viewRect.height-bounds.height;
				if (h < 0) h = -h;
				y = bounds.y-h/2;
			}
        } else {
        	//lens not centered
        	if (blockIncrement) return;
        	int w = viewRect.width-bounds.width;
			if (w < 0) w = -w;
			x = bounds.x-w/2;
			int h = viewRect.height-bounds.height;
			if (h < 0) h = -h;
			y = bounds.y-h/2;
        }
		vBar.setValue(y);
		hBar.setValue(x);
		//getViewport().setViewPosition(new Point(bounds.x, bounds.y));
		setBirdEyeViewLocation();
	}
	
	/**
	 * Sets the value of the horizontal and vertical scrollBars.
	 * 
	 * @param vValue	The value to set for the vertical scrollBar.
	 * @param hValue	The value to set for the horizontal scrollBar.
	 */
	void scrollTo(int vValue, int hValue)
	{
		//Rectangle viewRect = getViewport().getViewRect();
		//installScrollbarListener(false);
		JScrollBar vBar = getVerticalScrollBar();
		JScrollBar hBar = getHorizontalScrollBar();
		hBar.setValue(hBar.getValue()+hValue);
		vBar.setValue(vBar.getValue()+vValue);
		setBirdEyeViewLocation();
		//installScrollbarListener(true);
	}

	/** Clears the grid images. */
	void clearGridImages() { model.clearGridImages(); }
	
	/**
	 * Returns <code>true</code> if the user is adjusting the window,
	 * <code>false</code> otherwise.
	 * 
	 * @return See above.
	 */
	boolean isAdjusting() { return adjusting; }
	
	/** Locates the scroll bars. */
	void locateScrollBars()
	{
		if (!scrollbarsVisible()) return;
		scrollTo(getViewport().getViewRect(), false);
	}

	/**
	 * Returns the location of the bird eye view.
	 * 
	 * @return See above.
	 */
	int getBirdEyeViewLocationIndex()
	{
		if (birdEyeView == null) return -1;
		return birdEyeView.getLocationIndex();
	}
	
	/** Sets the adjusting value to <code>false</code>.*/
	void resetAdjusting() { adjusting = false; }
	
	/**
	 * Returns the rectangle used to load the tiles.
	 * 
	 * @return See above.
	 */
	Rectangle getVisibleRectangle()
	{
		return getViewport().getViewRect();
	}
	
	/**
	 * Sets the location of the bird eye to be sure that it is always visible.
	 * @see AdjustmentListener#adjustmentValueChanged(AdjustmentEvent)
	 */
	public void adjustmentValueChanged(AdjustmentEvent e)
	{
		if (e.getValueIsAdjusting()) {
        	adjusting = true;
        	setBirdEyeViewLocation();
        	setSelectionRegion();
        	return;
        }
        adjusting = false;
        //setSelectionRegion();
        setBirdEyeViewLocation();
        setSelectionRegion();
        model.checkTilesToLoad(getViewport().getViewRect());
	}
	
	/**
	 * Overridden to center the image.
	 * @see JComponent#setBounds(Rectangle)
	 */
	public void setBounds(Rectangle r)
	{
		setBounds(r.x, r.y, r.width, r.height);
	}
	
	/**
	 * Overridden to center the image.
	 * @see JComponent#setBounds(int, int, int, int)
	 */
	public void setBounds(int x, int y, int width, int height)
	{
		super.setBounds(x, y, width, height);
		Rectangle r = getViewport().getViewRect();
		Dimension d = layeredPane.getPreferredSize();
		if (model.isBigImage()) {
    		//setSelectionRegion();
			setBirdEyeViewLocation();
			if (!(d.width < r.width && d.height < r.height))
				return;
		}
		if (!scrollbarsVisible() && adjusting) adjusting = false;
		JScrollBar hBar = getHorizontalScrollBar();
		JScrollBar vBar = getVerticalScrollBar();
		if (!(hBar.isVisible() && vBar.isVisible())) center();
	}
	
}
