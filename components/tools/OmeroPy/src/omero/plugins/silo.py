#!/usr/bin/env python
"""
   Plugin for managing Silo data storage.

   Copyright 2011 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

from exceptions import Exception

from omero.cli import BaseControl
from omero.cli import CLI
from omero.util.decorators import wraps

import time

HELP="""Silo"""

SILO_NS = "openmicroscopy.org/silo/table"

LOAD_AUDIT_LOG = (""" select o.id, o.path, o.name, o.size
                        from OriginalFileAnnotationLink l join l.child.file o
                       where l.parent.id = %s and o.mimetype = 'OMERO.tables'
                         and o.name like '%%AuditLog'""", ("Id", "Path", "Name", "Size")) # FIXME

LOAD_SILOS = ("""     select o.id, o.path, o.name, o.size
                        from OriginalFile o
                       where o.mimetype = 'OMERO.silo' order by id desc""", ("Id", "Path", "Name", "Size"))

LOAD_TABLES = ("""    select l.child.file.id, l.child.file.path, l.child.file.name, l.child.file.size
                        from OriginalFileAnnotationLink l
                       where l.parent.id = %s and l.child.file is not null""", ("Id", "Path", "Name", "Size"))

SILO_FROM_TABLE = ("""select l.parent.id from OriginalFileAnnotationLink l where l.child.file.id = %s""", )


class SiloException(Exception):
    """
    Exception which can be thrown be the SiloApi and
    ensure proper handling via a SiloExceptionHandler.
    """

    def __init__(self, errno, msg):
        Exception.__init__(self)
        self.errno = errno
        self.msg = msg


def SiloExceptionHandler(func):
    """
    Decorator for handling SiloException
    """

    def handler(*args, **kwargs):
        self = args[0]
        try:
            return func(*args, **kwargs)
        except SiloException, se:
            self.ctx.die(se.errno, se.msg)

    handler = wraps(func)(handler)
    return handler


class SiloApi(object):
    """
    Public API for working with silos.

    These methods will eventually be pushed server side.
    """

    def __init__(self, client, event_context = None):
        self.client = client
        self.event_context = event_context
        if not self.event_context:
            self.event_context = \
            self.client.sf.getAdminService().getEventContext()

    def auditlog(self, silo_id, offset, limit):
        """
        Return audit log
        """

        table = self._auditlog(silo_id)
        data = self._tail(table, table, offset, limit)
        if data is None:
            raise SiloException(101, "No audit logs")
        return data

    def create(self, silo_name):
        """Initializes a fresh silo"""

        from omero.util.temp_files import create_path

        file = create_path()
        file.write_text(""" # Configuration
a = 1
b = 2
        """)

        ofile = self.client.upload(filename = file.abspath(), path = "/Silos", \
                name = silo_name, type = "OMERO.silo")

        return ofile.id.val

    def define(self, silo_id, name, cols, skip_audit = False):
        """
        Define a new type in the silo
        """

        from omero.model import OriginalFileI, FileAnnotationI, OriginalFileAnnotationLinkI
        from omero.rtypes import rstring

        us = self.client.sf.getUpdateService()
        sr = self.client.sf.sharedResources()

        if not skip_audit:
            auditlog = self._auditlog(silo_id)
        else:
            auditlog = None

        try:

            try:

                sz = 0
                if cols:
                    sz = len(cols)

                nt = sr.newTable(1, "/Silos/%s/%s" % (silo_id, name))
                if nt is None:
                    raise SiloException(154, "No table returned! %s" % args.name)

                try:
                    of = nt.getOriginalFile()
                    resource = self._resource(of)
                    fa = FileAnnotationI()
                    fa.ns = rstring(SILO_NS)
                    fa.file = of
                    fl = OriginalFileAnnotationLinkI()
                    fl.child = fa
                    fl.parent = OriginalFileI(str(silo_id), False)
                    fl = us.saveAndReturnObject(fl)
                    nt.initialize(cols)
                    if auditlog:
                        self._log(auditlog, resource, "CREATE", "%s col(s)" % sz)
                    return of
                finally:
                    nt.close()

            except:
                if auditlog:
                    self._log(auditlog, resource, "FAILED_CREATED", "%s col(s)" % sz)
                raise

        finally:
            if auditlog:
                auditlog.close()

    def headers(self, table_id):
        """
        Return headers for the table.
        """

        silo_id = self.silo_from_table(table_id)
        auditlog = self._auditlog(silo_id)
        try:
            table = self._open(table_id)
            try:
                try:
                    headers = table.getHeaders()
                    resource = self._resource(table.getOriginalFile())
                    sz = 0
                    if headers:
                        sz = len(headers)
                    self._log(auditlog, resource, "HEADERS", "%s col(s)" % sz)
                    return headers
                except:
                    self._log(auditlog, resource, "FAILED_HEADERS", "%s col(s)" % sz)
                    raise
            finally:
                table.close()
        finally:
            auditlog.close()

    def list(self, offset, limit):
        """
        Return available silos
        """
        return self._query(LOAD_SILOS[0], offset, limit)

    def silo_from_table(self, table_id):
        """
        Returns the unique silo id that this table id is attached to,
        or calls ctx.die otherwise.
        """
        rv = self._query(SILO_FROM_TABLE[0] % table_id, 0, 10)
        if len(rv) != 1:
            raise SiloException(103, "Invalid number of silos for table %s: %s" % (table_id, len(rv)))
        return rv[0][0]

    def tables(self, silo_id, offset, limit):
        """
        Return tables associated with this silo
        """
        return self._query(LOAD_TABLES[0] % silo_id, offset, limit)

    def tail(self, table_id, offset, limit):
        """
        """
        silo_id = self.silo_from_table(table_id)
        audit_log = self._auditlog(silo_id)
        try:
            table = self._open(table_id)
            try:
                data = self._tail(audit_log, table, offset, limit)
                if data is None:
                    raise SiloException(101, "No data")
                return data
            finally:
                table.close()
        finally:
            audit_log.close()

    def write(self, table_id, cols):
        """
        Write data into a table
        """
        silo_id = self.silo_from_table(table_id)
        auditlog = self._auditlog(silo_id)
        try:
            sink = self._open(table_id)
            resource = self._resource(sink.getOriginalFile())
            try:
                sz = 0
                if cols and cols[0].values:
                    sz = len(cols[0].values)
                try:
                    sink.addData(cols)
                    self._log(auditlog, resource, "WRITE", "%s row(s)" % sz)
                except:
                    self._log(auditlog, resource, "FAILED_WRITE", "%s row(s)" % sz)
                    raise
            finally:
                sink.close()
        finally:
            auditlog.close()

    #
    # Helpers
    #
    def _auditlog(self, silo_id):
        """
        Load the single audit log for the given silo
        """
        logs = self._query(LOAD_AUDIT_LOG[0] % silo_id, 0, 10)

        if len(logs) != 1:
            raise SiloException(100, "No single audit log found for silo %s! (size=%s)" % (silo_id, len(logs)))

        return self._open(logs[0][0])

    def _log(self, log, resource, action, message):
        cols = log.getHeaders()
        cols[0].values = [self.event_context.userId]
        cols[1].values = [long(time.time()*1000)]
        cols[2].values = [str(resource)]
        cols[3].values = [str(action)]
        cols[4].values = [str(message)]
        log.addData(cols)

    def _open(self, id):
        from omero.model import OriginalFileI

        sr = self.client.sf.sharedResources()
        return sr.openTable(OriginalFileI(id, False))

    def _query(self, query, offset, limit):
        import omero
        from omero.rtypes import unwrap
        q = self.client.sf.getQueryService()
        p = omero.sys.ParametersI()
        p.page(offset, limit)
        rv = unwrap(q.projection(query, p))
        return rv

    def _tail(self, auditlog, table, offset, limit):
        """
        Return 'limit' vailues from the end of table
        but skip up by 'offset'

        If no fewer rows are present, then all rows
        are returned. If no rows are present, None is
        returned.
        """
        if offset != 0:
            raise SiloException(111, "Non-zero offset currently unsupported")

        try:
            resource = self._resource(table.getOriginalFile())
            row_count = table.getNumberOfRows()
            if row_count == 0:
                return None

            if limit > row_count:
                limit = row_count

            rows = []
            for x in range(row_count - limit, row_count, 1):
                rows.append(x)

            data = table.readCoordinates(rows)
            self._log(auditlog, resource, "READ", "%s rows" % limit)
        except:
            self._log(auditlog, resource, "FAILED_READ", "%s rows" % limit)
            raise

        return data

    def _resource(self, ofile):
            return "Table:%s" % ofile.id.val

    #
    # Static Helpers
    #
    @staticmethod
    def stringify(data, headers = None):
        """
        Add data to an omero.util.text.TableBuilder instance
        and return it.
        """

        from omero.util.text import TableBuilder
        from omero.grid import Data

        if isinstance(data, Data):
            tb = TableBuilder(*tuple(["Row #"] + [x.name for x in data.columns]))
            for idx, row in enumerate(data.rowNumbers):
                values = [row]
                for x in data.columns:
                    values.append(x.values[idx])
                tb.row(*tuple(values))
        else:
            if headers is None:
                raise SiloException(321,\
                    "Excepted headers; found none for data: %s" % data)
            tb = TableBuilder(*headers)
            for row in data:
                tb.row(*row)
        return tb


class BaseParser(object):

    def __init__(self, parser):
        parts = parser.split(".")
        mod = __import__(".".join(parts[:-1]))
        for x in parts[1:-1]:
            mod = getattr(mod, x)
        self.kls = getattr(mod, parts[-1])


class ParserDefiner(BaseParser):

    def __call__(self, args):
        xml = []
        csv = []
        for arg in args:
            if arg.endswith("xml"):
                xml.append(arg)
            else:
                csv.append(arg)

        if len(xml) != 1:
            raise Exception("Expecting exactly one XML file arg. Not %s" % " ".join(args))

        instance = self.kls(xml[0])
        return (instance, csv)


class SiloLoader(object):

    def __init__(self, ctx):
        self.ctx = ctx

    def __repr__(self):
        val = self.ctx.read_config("silo", "default_id")
        return "%s" % val


class SiloControl(BaseControl):

    def _configure(self, parser):
        sub = parser.sub()

        parser.add(sub, self.demo)
        list = parser.add(sub, self.list)

        default = parser.add(sub, self.default)
        default.add_argument("silo_id", nargs="?", help="value to set default; otherwise prints current")

        create = parser.add(sub, self.create)
        create.add_argument("name", help="name of the silo (OriginalFile.name)")

        define = parser.add(sub, self.define)
        auditlog = parser.add(sub, self.auditlog)
        tables = parser.add(sub, self.tables)
        for x in (define, auditlog, tables):
            x.add_argument("--id", type=long, default=SiloLoader(self.ctx), help="id of the selected silo")
        define.add_argument("name", help="name of the new table")
        define.add_argument("arg", nargs="*", help="column descriptors of the form 'type:name:param=value'")
        define.add_argument("--parser", type=ParserDefiner, help="parser class which should be used on all args")

        load = parser.add(sub, self.load)
        describe = parser.add(sub, self.describe)
        tail = parser.add(sub, self.tail)
        for x in (load, describe, tail):
            x.add_argument("id", type=long, help="id of the selected table")
        load.add_argument("arg", nargs="*", help="data files'")

        for x in (auditlog, tables, tail, list):
            x.add_argument("--limit", type=int, default=25, help="limit the number of return rows")
            x.add_argument("--offset", type=int, default=0, help="number of rows to skip")

    @SiloExceptionHandler
    def demo(self, args):
        """
        Run a full, example silo workflow

        The demo will create a silo named "Demo", add tables to it,
        add random data, and then display that data via "tail".
        """

        silo = self.silo_api(args)

        self.ctx.out("\nExample silo session")
        self.ctx.out("="*80)

        commands = []
        commands.append(self._demo("List current silos", self.list))
        commands.append(self._demo("Create new silo", self.create, "Demo"))
        silo_id = self.ctx.get("rv")
        commands.append(self._demo("Re-list silos", self.list))

        commands.append(self._demo("Add user table to silo %s" % silo_id,
            self.define, "--id", str(silo_id),\
            "TypeA", "String:personal_id:size=12", \
            "Long:measurement_1", "Long:measurement_2"))

        of = self.ctx.get("rv")
        table_id = of.id.val
        self._demo("Add random data to table %s" % table_id)

        cs = silo.headers(table_id)
        for c in cs:
            c.values = []
        for x in range(50):
            cs[0].values.append(("%s" % x) * 12)
            cs[1].values.append(x)
            cs[2].values.append(-x)
        silo.write(table_id, cs)

        commands.append(self._demo("List tables attached to silo", \
                self.tables, "--id", str(silo_id)))
        commands.append(self._demo("List last several lines of table %s" % \
            of.id.val, self.tail, str(of.id.val)))
        commands.append(self._demo("List audit log", \
                self.auditlog, "--id", str(silo_id)))
        commands.append(self._demo("List audit log again", \
                self.auditlog, "--id", str(silo_id)))

        delete = self.ctx.controls["delete"]
        commands.append(delete._demo("Deleting silo %s" % silo_id, delete, "/OriginalFile:%s" % silo_id))
        commands.append(self._demo("List current silos", self.list))

        self.ctx.out("Summary of demo:")
        self.ctx.out("="*80)
        for command in commands:
            if command:
                print "omero", " ".join(command)

    @SiloExceptionHandler
    def default(self, args):
        """read and write the current default silo id
        """
        if args.silo_id is not None:
            self.ctx.write_config("silo", "default_id", args.silo_id)
        else:
            val = self.ctx.read_config("silo", "default_id")
            if val:
                self.ctx.out(val)

    @SiloExceptionHandler
    def create(self, args):
        """Initializes a fresh silo"""

        silo = self.silo_api(args)
        silo_id = silo.create(args.name)
        self.ctx.out("Created silo %s" % silo_id)

        new_args = args.__class__()
        new_args.id = silo_id
        new_args.name = "AuditLog"
        new_args.arg = ["Long:user_id", "Long:timestamp",\
                "String:resource:size=100", "String:action:size=100", "String:message:size=100"]
        new_args.parser = None
        self.define(new_args, skip_audit = True)

        self.ctx.set("rv", silo_id)
        return silo_id

    @SiloExceptionHandler
    def define(self, args, skip_audit = False):
        """Define a new type in the silo"""

        from omero.grid import StringColumn, LongColumn

        col_types = {"String": (StringColumn, {"size": int}), "Long": (LongColumn, dict())}

        if args.parser:
            try:
                parser, csv = args.parser(args.arg)
                parser.initialize(nt, data=csv)
            except Exception, e:
                import traceback
                self.ctx.dbg(traceback.format_exc(e))
                self.ctx.die(33, "Parser error: %s" % e)
        else:
            cs = []
            for arg in args.arg:
                parts = arg.split(":")
                type = parts[0]
                cfg = col_types[type]

                column = cfg[0]()
                mappers = cfg[1]

                column.name = parts[1]

                params = parts[2:]
                for idx, param in enumerate(params):
                    parts = param.split("=", 1)
                    if len(parts) == 1:
                        parts.append("")
                    param = parts[0]
                    value = parts[1]
                    if param in mappers:
                        value = mappers[param](value)
                    setattr(column, param, value)

                cs.append(column)

        silo = self.silo_api(args)
        ofile = silo.define(args.id, args.name, cs, skip_audit = skip_audit)

        self.ctx.out("Created table %s ('%s')" % (ofile.id.val, args.name))
        self.ctx.set("rv", ofile)

    @SiloExceptionHandler
    def load(self, args):
        """Load data into a table
        """
        from matplotlib.mlab import csv2rec
        silo = self.silo_api(args)

        for arg in args.arg:
            cols = silo.headers() # Fresh each time
            records = csv2rec(arg, delimiter="|") # TODO: configuration should come from file
            for rec in records:
                for idx, col in enumerate(cols):
                    col.values.append(rec[idx])
            silo.write(args.id, cols)

    @SiloExceptionHandler
    def auditlog(self, args):
        """Display audit log
        """

        silo = self.silo_api(args)

        data = silo.auditlog(args.id, args.offset, args.limit)
        self.ctx.out(silo.stringify(data))

    @SiloExceptionHandler
    def list(self, args):
        """List available silos"""

        silo = self.silo_api(args)

        rv = silo.list(args.offset, args.limit)
        self.ctx.out(silo.stringify(rv, LOAD_SILOS[1]))

    @SiloExceptionHandler
    def tables(self, args):
        """List tables associated with this silo"""

        silo = self.silo_api(args)

        rv = silo.tables(args.id, args.offset, args.limit)
        self.ctx.out(silo.stringify(rv, LOAD_TABLES[1]))

    @SiloExceptionHandler
    def describe(self, args):
        """Describe the contents of a table"""

        silo = self.silo_api(args)

        headers = silo.headers(args.id)
        print headers

    @SiloExceptionHandler
    def tail(self, args):
        """List the last several entries of the table"""

        silo = self.silo_api(args)

        table_id = args.id
        data = silo.tail(table_id, args.offset, args.limit)
        if data is None:
            self.ctx.die(101, "No data")
        self.ctx.out(silo.stringify(data))

    def silo_api(self, args):
        self.ctx.conn(args)
        silo = SiloApi(self.ctx._client, self.ctx._event_context)
        return silo


try:
    register("silo", SiloControl, HELP)
except NameError:
    if __name__ == "__main__":
        import sys
        cli = CLI()
        cli.register("silo", SiloControl, HELP)
        cli.invoke(sys.argv[1:])
