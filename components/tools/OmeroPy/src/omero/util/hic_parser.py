#!/usr/bin/env python
# encoding: utf-8
"""
::

   Copyright 2011 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import re
import os
import sys
import logging

import xml.dom.minidom

try:
    from xml.etree.ElementTree import XML, Element, SubElement, Comment, ElementTree, tostring
except ImportError:
    from elementtree.ElementTree import XML, Element, SubElement, Comment, ElementTree, tostring

from omero.grid import *


class Column(object):
    """
    Single element from XPath /schema/columns/column
    Attributes and subelements are added as fields
    """

    def __init__(self, element = None, **kwargs):
        if element is not None:
            self.pos = element.attrib["pos"]
            for x in ("name", "type", "descriptor"):
                setattr(self, x, element.find(x).text)
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "%s(pos='%s', name='%s', type='%s', descriptor='%s')" %\
            (self.__class__.__name__, self.pos, self.name, self.type, self.descriptor)


class SchemaXml(object):
    """

    """
    attributes = ("filename", "datecreated", "linecount", "filesize",\
            "separator", "dateformat", "descriptor", "comment")

    def __init__(self, file = None, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)    #: Logs to the class name
        if file is not None:
            self.source = open(file, "r")                               #: Open file handle
            self.text = self.source.read()
            self.XML = XML(self.text)
            self.summary = self.XML.find("summary")
            for x in SchemaXml.attributes:
                setattr(self, x, self.summary.find(x).text)
            self.columns = [Column(col) for col in self.XML.find("columns").findall("./column")]
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def initialize(self, table):
        cs = []
        for col in self.columns:
            print col
            cs.append(StringColumn(\
                name=col.name, description=self.descriptor, size=100, values=[]))
        table.initialize(cs)
        return cs

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        contents = ""
        for attribute in SchemaXml.attributes:
            contents += "  %s = '%s',\n" % (attribute, getattr(self, attribute, ""))
        contents += "  columns = [\n"
        contents += ",\n".join(["    " + str(x) for x in self.columns])
        contents += "\n  ]\n"
        return """%s(
%s)""" % (self.__class__.__name__, contents)


if __name__ == "__main__":
    for x in sys.argv[1:]:
        print SchemaXml(x)
