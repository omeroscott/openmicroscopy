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
            ("separator", "|"), "dateformat", "descriptor", "comment")

    def __init__(self, file = None, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)    #: Logs to the class name
        if file is not None:
            self.source = open(file, "r")                               #: Open file handle
            self.text = self.source.read()
            self.XML = XML(self.text)
            self.summary = self.XML.find("summary")
            for x in SchemaXml.attributes:
                default = None
                if isinstance(x, tuple):
                    x, default = x # Unwrap defaults
                val = self.summary.find(x).text
                if default and not val:
                    val = default
                setattr(self, x, val)
            self.columns = [Column(col) for col in self.XML.find("columns").findall("./column")]
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def map_dtype(self, dtype):
        kind = dtype.kind
        if kind == "S":
            return StringColumn()
        elif kind == "O":
            # Assuming date
            return LongColumn()
        elif kind == "i":
            return LongColumn()
        else:
            raise Exception(kind)

    def map_schema(self, type):
        #
        # varchar, char, date, int
        #
        raise Exception(type)

    def check_dtype(self, col, dtype):
        assert isinstance(self.map_dtype(dtype), col.__class__)

    def check_schema(self, col, type):
        if not type:
            return
        elif type in ("varchar", "char"):
            assert isinstance(col, StringColumn)
        elif type == "date":
            assert isinstance(col, LongColumn)
        elif type == "int":
            assert isinstance(col, LongColumn)
        else:
            raise Exception(type)

    def initialize(self, table, data = None):
        from matplotlib.mlab import csv2rec
        cs = None
        if data:
            for csv in data:
                records = csv2rec(csv, delimiter=self.separator)
                types = records.dtype
                if cs is None:
                    cs = [self.map_dtype(x) for x in [types[i] for i in range(len(types))]]
                else:
                    if len(types) != len(cs):
                        raise Exception("len(types)==%1 <> len(columns)==%1" % (len(types), len(cs)))
                    for idx, type in enumerate(types):
                        self.check_dtype(cs[idx], type)

        if cs is None:
            cs = [self.map_schema(col.type) for col in columns]
        else:
            for idx, col in enumerate(self.columns):
                self.check_schema(cs[idx], col.type)

        # Handle name, etc
        for idx, col in enumerate(self.columns):
            c = cs[idx]
            c.name = col.name
            c.description = col.descriptor
            if isinstance(c, StringColumn):
                c.size = 100

        table.initialize(cs)

        import time
        import datetime
        def epoch(dt):
            return long(time.mktime(dt.timetuple())*1000)

        if data:
            for csv in data:
                cs = table.getHeaders()
                records = csv2rec(csv, delimiter=self.separator)
                dtype = records.dtype
                for x in range(len(dtype)):
                    if isinstance(records[dtype.names[x]][0], datetime.date): # FIXME
                        cs[x].values = [epoch(dt) for dt in records[dtype.names[x]]]
                    else:
                        cs[x].values = records[dtype.names[x]].tolist()
                table.addData(cs)

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
