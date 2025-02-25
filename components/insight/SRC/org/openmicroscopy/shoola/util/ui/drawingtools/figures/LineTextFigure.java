/*
 * org.openmicroscopy.shoola.util.ui.drawingtools.figures.LineTextFigure 
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
package org.openmicroscopy.shoola.util.ui.drawingtools.figures;

// Java imports
import java.awt.Color;
import java.awt.Font;
import java.awt.FontMetrics;
import java.awt.Graphics2D;
import java.awt.font.TextLayout;
import java.awt.geom.Point2D;
import java.awt.geom.Rectangle2D;

// Third-party libraries
import org.jhotdraw.draw.AttributeKeys;
import org.jhotdraw.draw.LineFigure;
import org.jhotdraw.draw.TextHolderFigure;
import org.jhotdraw.draw.Tool;
import org.jhotdraw.geom.Insets2D;

// Application-internal dependencies
import org.openmicroscopy.shoola.util.ui.drawingtools.attributes.DrawingAttributes;
import org.openmicroscopy.shoola.util.ui.drawingtools.texttools.DrawingTextTool;


/**
 * A line figure with text.
 * 
 * @author Jean-Marie Burel &nbsp;&nbsp;&nbsp;&nbsp; <a
 *         href="mailto:j.burel@dundee.ac.uk">j.burel@dundee.ac.uk</a>
 * @author Donald MacDonald &nbsp;&nbsp;&nbsp;&nbsp; <a
 *         href="mailto:donald@lifesci.dundee.ac.uk">donald@lifesci.dundee.ac.uk</a>
 * @version 3.0 <small> (<b>Internal version:</b> $Revision: $Date: $)
 *          </small>
 * @since OME3.0
 */
public class LineTextFigure 
	extends LineFigure 
	implements TextHolderFigure
{
	
	/** Flag indicating if the figure is editable or not. */
	private boolean 				editable;

	/** Cache of the TextFigure's layout. */
	transient private  	TextLayout	textLayout;
	
	/** The bounds of the text. */
	private Rectangle2D.Double		textBounds;

	/**
	 * Returns the layout used to lay out the text.
	 * 
	 * @return See above.
	 */
	private TextLayout getTextLayout()
	{
		if (textLayout == null) 
			textLayout = FigureUtil.createLayout(getText(), 
								getFontRenderContext(), getFont(), 
								AttributeKeys.FONT_UNDERLINE.get(this));
		return textLayout;
	}
	
	/**
	 * Creates a new instance.
	 * 
	 * @param text The text to display.
	 */
	public LineTextFigure(String text)
	{
		super();
		setText(text);
		textLayout = null;
		textBounds = null;
		editable = true;
	}
	
	/**
	 * Sets the editable flag.
	 * 
	 * @param b Passed <code>true</code> to be editable, <code>false</code>
	 * 			otherwise.
	 */
	public void setEditable(boolean b) { this.editable = b; }
	
	/** 
	 * Returns the bounds of the text.
	 * 
	 * @return See above.
	 */
	protected Rectangle2D.Double getTextBounds() 
	{
		if (textBounds == null) return new Rectangle2D.Double(0, 0, 0, 0);
		else return textBounds;
	}
	
	/**
	 * Overridden to draw the text.
	 * @see LineFigure#drawFill(Graphics2D)
	 */
	protected void drawFill(Graphics2D g)
	{
		super.drawFill(g);
		drawText(g);
	}

	/**
	 * Overridden to control if the passed point is within the bounds.
	 * @see LineFigure#contains(Point2D.Double)
	 */
	public boolean contains(Point2D.Double p)
	{
		return getBounds().contains(p);
	}
	
	/**
	 * Overridden to draw the text.
	 * @see LineFigure#drawText(Graphics2D)
	 */
	protected void drawText(Graphics2D g)
	{
		if (!(DrawingAttributes.SHOWTEXT.get(this))) return;
		String text = getText();
		if (text != null)//  && isEditable()) 
		{	
			text = text.trim();
			TextLayout layout = getTextLayout();
			Rectangle2D.Double r = getBounds();
			Font font = AttributeKeys.FONT_FACE.get(this);
			FontMetrics fm = g.getFontMetrics(font);
			double textWidth = fm.stringWidth(text);
			double textHeight = fm.getAscent();
			double x = r.x+r.width/2-textWidth/2;
			double y = r.y+textHeight/2+r.height/2;
			
			Font viewFont = 
				font.deriveFont(AttributeKeys.FONT_SIZE.get(this).intValue());
			g.setFont(viewFont);
			g.setColor(AttributeKeys.TEXT_COLOR.get(this));
			textBounds = new Rectangle2D.Double(x, y, textWidth, textHeight);
			layout.draw(g, (float) textBounds.x, (float) textBounds.y);
		}
	}

	/** 
	 * Overridden to set the layout to <code>null</code>.
	 * @see LineFigure#invalidate()
	 */
	public void invalidate() 
	{
		super.invalidate();
		textLayout = null;
	}

	/** 
	 * Overridden to set the layout to <code>null</code>.
	 * @see LineFigure#validate()
	 */
	protected void validate() 
	{
		super.validate();
		textLayout = null;
	}
	
	/**
	 * Overridden to return the bounds of the text area.
	 * @see LineFigure#getDrawingArea()
	 */
	public Rectangle2D.Double getDrawingArea()
	{
		Rectangle2D.Double r = super.getDrawingArea();
		r.add(getTextBounds());
		return r;
	}
	
	/**
	 * Overridden to set the correct tool.
	 * @see LineFigure#getTool(Point2D.Double)
	 */
	public Tool getTool(Point2D.Double p)
	{
		boolean showText = false;
		if (isEditable() && getBounds().contains(p)) showText = true;
		
		if (super.path != null && showText)
		{
			if (super.path.outlineContains(p, 5.0)) showText = false;
		}
		if (showText) {
			invalidate();
			return new DrawingTextTool(this);
		}
		return null;
	}
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getText()
	 */
	public String getText()
	{ 
		return (String) getAttribute(AttributeKeys.TEXT); 
	}
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#setText(String)
	 */
	public void setText(String newText) 
	{
		boolean b = (newText != null && newText.trim().length() > 0);
		setAttribute(DrawingAttributes.SHOWTEXT, b);
		setAttribute(AttributeKeys.TEXT, newText);
	}
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getTextColumns()
	 */
	public int getTextColumns() 
	{
		String t = getText();
		int n = FigureUtil.TEXT_COLUMNS;
		return (t == null) ? n : Math.max(t.length(), n);
	}
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getTabSize()
	 */
	public int getTabSize() { return FigureUtil.TAB_SIZE; }
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getLabelFor()
	 */
	public TextHolderFigure getLabelFor() { return this; }
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getInsets()
	 */
	public Insets2D.Double getInsets() { return new Insets2D.Double(); }

	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getFont()
	 */
	public Font getFont() { return AttributeKeys.getFont(this); }
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getTextColor()
	 */
	public Color getTextColor() { return AttributeKeys.TEXT_COLOR.get(this); }
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getFillColor()
	 */
	public Color getFillColor() { return AttributeKeys.FILL_COLOR.get(this); }
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#getFontSize()
	 */
	public float getFontSize()
	{
		return AttributeKeys.FONT_SIZE.get(this).floatValue();
	}
	
	/**
	 * Implemented as specified by the {@link TextHolderFigure} I/F.
	 * @see TextHolderFigure#isEditable()
	 */
	public boolean isEditable() { return editable; }

	/**
	 * Required by the {@link TextHolderFigure} I/F but no-op implementation
	 * in our case.
	 * @see TextHolderFigure#setFontSize(float)
	 */
	public void setFontSize(float size)  {}

	/* (non-Javadoc)
	 * @see org.jhotdraw.draw.TextHolderFigure#isTextOverflow()
	 */
	public boolean isTextOverflow()
	{
		// TODO Auto-generated method stub
		return false;
	}
	
	/**
	 * Get the number of points in the line. 
	 */
	public int getPointCount()
	{
		return getNodeCount();
	}
	
	/*
	 * (non-Javadoc)
	 * @see org.openmicroscopy.shoola.util.ui.drawingtools.figures.
	 * LineFigure#clone()
	 */
	public LineTextFigure clone()
	{
		LineTextFigure that = (LineTextFigure) super.clone();
		that.setText(this.getText());
		return that;
	}
	
}
