#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2011 Glencoe Software, Inc. All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

"""
Conversion from SQL to OMERO.tables actions.
"""

import numpy
import tables
import tempfile
import traceback
import unittest

import sqlparse

from sqlparse.sql import IdentifierList, Identifier, Where, Parenthesis
from sqlparse.tokens import DML, Keyword, Newline, Punctuation, Whitespace, Wildcard


SQL_TEMPLATE = """
            SELECT %(select)s
              FROM %(from)s
             WHERE %(where)s
          GROUP BY %(groupby)s
          ORDER BY %(orderby)s
             LIMIT %(limit)s
            OFFSET %(offset)s
"""

class Aggregate(object):

    def __init__(self, func, contents):
        self.func = func
        self.contents = contents

    def to_unicode(self):
        return "%s(%s)" % (self.func.to_unicode(), ", ".join([x.to_unicode() for x in self.contents]))


class ParserException(Exception): pass
class Unsupported(ParserException): pass
class Internal(ParserException): pass
class Invalid(ParserException): pass


class Parser(object):

    def __init__(self, sql):
        self.sql = sql
        self.parsed = sqlparse.parse(sql)
        if len(self.parsed) != 1:
            raise Unsupported("Wrong number of statements: %s", len(self.parsed))
        self.statement = self.parsed[0]
        self.all_tokens = self.statement.tokens

        self.tokens = [x for x in self.all_tokens if not self.skip(x)]
        if not self.is_select(self.tokens[0]):
            raise Unsupported("Statement does not begin with 'select'")

        self.define_parts()
        self.define_tables()

    def execute(self, source):
        # Check for aggregates
        select = self.parts["select"]
        _from = self.parts["from"]
        for x in select:
            if isinstance(x, Aggregate):
                if len(select) != 1:
                    raise Unsupported("Count and columns not yet supported: %s", self)
                elif not x.func.match(Keyword, "count"):
                    raise Unsupported("Unsupported aggregation: %s", self)
                elif len(_from) != 1:
                    raise Unsupported("Too many tables for count: %s", self)
                else:
                    target =  _from[0].get_name()
                    return source.nrows(target)
        # No aggregates
        assert not self.parts["where"]
        assert not self.parts["groupby"]
        assert not self.parts["orderby"]
        assert not self.parts["limit"]
        assert not self.parts["offset"]
        self.resolve_columns(source)
        assert len(self.tables) == 1
        return source.get_table(self.tables[0])[:].tolist()

    def resolve_columns(self, source):

        table_names = source.get_table_names()
        column_names = dict([(x, source.get_column_names(x)) for x in table_names])
        reverse_column_names = dict()
        for table_name in table_names:
            for column_name in column_names[table_name]:
                try:
                    reverse_column_names[column_name].append(table_name)
                except KeyError:
                    reverse_column_names = {column_name:[table_name]}

        wc_token_lists = (self.parts["select"], )
        nowc_token_lists = (self.parts["where"], self.parts["groupby"], self.parts["orderby"])
        column_token_lists = tuple(list(wc_token_lists) + list(nowc_token_lists))

        for tokens in wc_token_lists:
            for token in tokens:
                if self.is_id(token):
                    # Handle prefixed
                    if len(token.tokens) == 3:
                        prefix = token.tokens[0].to_unicode()
                        value = token.tokens[2]
                        # Handle wildcards with prefixes
                        if value.ttype is Wildcard:
                            pass
                    # Handle unprefixed
                    elif len(token.tokens) == 1:
                        value = token.tokens[0]
                    else:
                        raise Unsupported("Unknown wildcard format: %s" % token.to_unicode())

        # Now all wildcards are resolved. Prefix all unprefixed columns
        for tokens in column_token_lists:
            for token in tokens:
                if self.is_id(token):
                    if len(token.tokens) == 3:
                        prefix = token.tokens[0].to_unicode()
                        value = token.tokens[2].to_unicode()
                        if token.tokens[2].ttype is Wildcard:
                            print "SKIPPING..."
                        elif value not in column_names[prefix]:
                            raise Invalid("No column found: %s.%s" % (prefix, value))
                    elif len(token.tokens) == 1:
                        if token.tokens[0].ttype is Wildcard:
                            print "SKIPPING..."
                        else:
                            value = token.tokens[0].to_unicode()
                            try:
                                tables = reverse_column_names[value]
                                if len(tables) != 1:
                                    raise Invalid("Non-unique column name: %s (%s)" % (value, ", ".join(tables)))
                            except KeyError:
                                raise Invalid("Unknown column: %s", value)

                    else:
                        raise Unsupported("Unknown wildcard format: %s" % token.to_unicode())

    def __str__(self):
        rv = """Parser(sql='%s',
            %s""" % (self.sql, SQL_TEMPLATE)
        return rv % dict([(k, " ".join([x.to_unicode() for x in v])) for k, v in self.parts.iteritems()])

    ##
    ## Definers
    ##

    def define_parts(self):
        """
        Split into: %s
        """ % SQL_TEMPLATE
        self.parts = {
            "select":[],
            "from":[],
            "where":[],
            "groupby":[],
            "orderby":[],
            "limit":[],
            "offset":[],
        }

        current = None
        tokens = list(self.tokens)
        while tokens:
            token = tokens.pop(0)
            if current == None:
                current = self.parts["select"]
                continue
            elif self.is_("from", token):
                current = self.parts["from"]
                continue
            elif self.is_where_clause(token):
                for subtoken in token.tokens:
                    if self.skip(subtoken):
                        continue
                    elif self.is_("where", subtoken):
                        continue
                    else:
                        self.parts["where"].append(subtoken)
            elif self.is_("group", token):
                by = tokens.pop(0)
                if not self.is_("by", by):
                    raise Unsupported("Expecting 'by'. Found: %s", by)
                current = self.parts["groupby"]
            elif self.is_("order", token):
                by = tokens.pop(0)
                if not self.is_("by", by):
                    raise Unsupported("Expecting 'by'. Found: %s", by)
                current = self.parts["orderby"]
            elif self.is_("limit", token):
                current = self.parts["limit"]
            elif self.is_("offset", token):
                current = self.parts["offset"]
            elif isinstance(token, IdentifierList):
                for subtoken in token.tokens:
                    if self.skip(subtoken):
                        continue
                    else:
                        current.append(subtoken)
            elif token.match(Keyword, "count"):
                while True:
                    next_token = tokens.pop(0)
                    if self.skip(next_token):
                        continue
                    elif self.is_parens(next_token):
                        agg = Aggregate(token, [subtoken for subtoken in next_token.tokens if not self.skip(subtoken)])
                        current.append(agg)
                        break
            else:
                current.append(token)


    def define_tables(self):
        stream = self.extract_from_part(self.statement)
        self.tables = list(self.extract_table_identifiers(stream))

    ##
    ## Keyword/clause detection methods
    ##

    def skip(self, token):
        return token.ttype is Whitespace or token.ttype is Newline or token.ttype is Punctuation

    def is_select(self, token):
        return token.ttype is DML and token.value.upper() == 'SELECT'

    def is_subselect(self, parsed):
        if not parsed.is_group():
            return False
        for item in parsed.tokens:
            if self.is_select(item):
                return True
        return False

    def is_(self, keyword, token):
        return token.ttype is Keyword and token.value.upper() == keyword.upper()

    def is_id(self, token):
        return isinstance(token, Identifier)

    def is_where_clause(self, token):
        return isinstance(token, Where)

    def is_parens(self, token):
        return isinstance(token, Parenthesis)

    def extract_from_part(self, parsed):
        from_seen = False
        for item in parsed.tokens:
            if from_seen:
                if self.is_subselect(item):
                    for x in self.extract_from_part(item):
                        yield x
                else:
                    yield item
            elif item.ttype is Keyword and item.value.upper() == 'FROM':
                from_seen = True

    def extract_table_identifiers(self, token_stream):
        for item in token_stream:
            if isinstance(item, IdentifierList):
                for identifier in item.get_identifiers():
                    yield identifier.get_name()
            elif isinstance(item, Identifier):
                yield item.get_name()
            # It's a bug to check for Keyword here, but in the example
            # above some tables names are identified as keywords...
            elif item.ttype is Keyword:
                yield item.value


class HdfDataSource(object):

    def __init__(self, descriptors):
        self.filenames = {}
        self.files = {}
        self.descriptors = descriptors

        for table, record in self.descriptors.iteritems():
            filename = tempfile.mktemp(suffix='.h5')
            self.filenames[table] = filename
            file = tables.openFile(filename, 'w', title="test: table")
            self.files[table] = file
            file.createTable("/", table, record)

    def close(self):
        for table, file in self.files.iteritems():
            try:
                file.close()
            except:
                traceback.print_exc()

    def get_table(self, table):
        table = getattr(self.files[table].root, table)
        return table

    def add(self, table, values):
        table = self.get_table(table)
        vals = []
        names = []
        for k, v in values.iteritems():
            names.append(k)
            vals.append(v)
        records = numpy.rec.fromarrays(vals, names=names)
        table.append(records)
        table.flush()

    def nrows(self, table):
        table = self.get_table(table)
        return table.nrows

    def get_table_names(self):
        return self.descriptors.keys()

    def get_column_names(self, table):
        t = self.get_table(table)
        return t.cols._v_colnames


class Test(unittest.TestCase):

    def data(self, *args, **kwargs):
        if not hasattr(self, "data_sources"):
            self.data_sources = []
        source = HdfDataSource(*args, **kwargs)
        self.data_sources.append(source)
        return source

    def testFailOnMultiStatements(self):
        self.assertRaises(Unsupported, Parser, "select * from bp; select * from chi")

    def testFailNonSelect(self):
        self.assertRaises(Unsupported, Parser, "update bp set date = 1")
        self.assertRaises(Unsupported, Parser, "delete from bp")
        self.assertRaises(Unsupported, Parser, "insert into bp")

    def testSimpleLoad(self):
        p = Parser("select * from bp")
        self.assertEquals(["bp"], p.tables)
        self.assertEquals(Wildcard, p.parts["select"][0].ttype)

    def testSimpleLoadWithPrefi(self):
        p = Parser("select bp.* from bp")
        self.assertEquals(["bp"], p.tables)
        self.assertEquals(Identifier, p.parts["select"][0].__class__)

    def testDefineParts(self):
        p = Parser("select a, b from c where d group by g limit 10")
        m = {"select": 2, "from": 1, "where": 1, "groupby": 1, "limit": 1}
        self.assertParts(p.parts, **m)

    def testCount(self):
        p = Parser("select count(a) from b")
        m = {"select": 1, "from": 1}
        self.assertParts(p.parts, **m)

    # With HDF Files

    def testSimpleCount(self):
        p = Parser("select count(*) from bp")
        self.assertEquals(["bp"], p.tables)
        source = self.data({"bp": {"a": tables.Int64Col()}})
        source.add("bp", {"a":[(1,),(2,),(3,)]})
        result = p.execute(source)
        self.assertEquals([[3]], result)

    def testSimpleCountWithGrouping(self):
        p = Parser("select a, count(*) from bp group by a")
        source = self.data({"bp": {"a": tables.Int64Col()}})
        source.add("bp", {"a":[(1,),(2,),(3,)]})
        self.assertRaises(Unsupported, p.execute, source)

    def testColumnsInTablePass(self):
        p = Parser("select a from bp")
        source = self.data({"bp": {"a": tables.Int64Col()}})
        source.add("bp", {"a":[(1,),(2,)]})
        result = p.execute(source)
        self.assertEquals([(1,), (2,)], result)

    def testColumnsInTableFail(self):
        p = Parser("select MISSING from bp")
        source = self.data({"bp": {"a": tables.Int64Col()}})
        source.add("bp", {"a":[(1,),(2,)]})
        self.assertRaises(Invalid, p.execute, source)

    def testWildcard(self):
        p = Parser("select * from bp")
        a = tables.Int64Col(pos=0)
        b = tables.Int64Col(pos=1)
        source = self.data({"bp": {"a":a, "b":b}})

        a = [(1,),(2,)]
        b = [(3,),(4,)]
        source.add("bp", {"a":a, "b":b})
        result = p.execute(source)
        self.assertEquals([(1,3), (2,4)], result)

    def testSpeciicWildcard(self):
        p = Parser("select bp.* from bp")
        a = tables.Int64Col(pos=0)
        b = tables.Int64Col(pos=1)
        source = self.data({"bp": {"a":a, "b":b}})

        a = [(1,),(2,)]
        b = [(3,),(4,)]
        source.add("bp", {"a":a, "b":b})
        result = p.execute(source)
        self.assertEquals([(1,3), (2,4)], result)

    def testAliasWildcard(self):
        p = Parser("select bp.* from bp_long_name as bp ")
        a = tables.Int64Col(pos=0)
        b = tables.Int64Col(pos=1)
        source = self.data({"bp_long_name": {"a":a, "b":b}})

        a = [(1,),(2,)]
        b = [(3,),(4,)]
        source.add("bp_long_name", {"a":a, "b":b})
        result = p.execute(source)
        self.assertEquals([(1,3), (2,4)], result)

    def assertParts(self, parts, **kwargs):
        for k, v in kwargs.iteritems():
            val = parts[k]
            sz = len(val)
            self.assertEquals(v, sz, "%s mismatch: %s <> %s: %s" % (k, v, sz, val))

    def tearDown(self):
        unittest.TestCase.tearDown(self)
        if hasattr(self, "data_sources"):
            for x in self.data_sources:
                try:
                    x.close()
                except:
                    traceback.print_exc()

    """Tests to write:
    def testFromAliasInWildCardSelect(self):
    """

if __name__ == '__main__':
    unittest.main()
    if "TRACE" in os.environ:
        import trace
        tracer = trace.Trace(ignoredirs=[sys.prefix, sys.exec_prefix], trace=1)
        tracer.runfunc(unittest.main)
    else:
        unittest.main()
