#!/usr/bin/env python
"""
   Plugin for managing Silo data storage.

   Copyright 2011 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

from exceptions import Exception

from omero.cli import BaseControl
from omero.cli import CLI
from omero.cli import VERSION

from omero_ext.argparse import FileType

from path import path

import omero.java
import time

HELP="""Silo"""

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

SILO_FROM_TABLE = ("""select l.parent.id from OriginalFileAnnotationLink l where l.child.file.id = %s""",)


class SiloControl(BaseControl):

    def _configure(self, parser):
        sub = parser.sub()

        demo = parser.add(sub, self.demo)

        create = parser.add(sub, self.create)
        create.add_argument("name", help="name of the silo (OriginalFile.name)")

        define = parser.add(sub, self.define)
        define.add_argument("id", help="id of the selected silo")
        define.add_argument("name", help="name of the new table")
        define.add_argument("arg", nargs="*", help="column descriptors of the form 'type:name:param=value'")

        auditlog = parser.add(sub, self.auditlog)
        auditlog.add_argument("id", help="id of the selected silo")

        list = parser.add(sub, self.list)

        tables = parser.add(sub, self.tables)
        tables.add_argument("id", help="id of the selected silo")

        tail = parser.add(sub, self.tail)
        tail.add_argument("id", type=long, help="id of the selected table")
        tail.add_argument("--count", type=int, default=25, help="number of rows")

    def demo(self, args):
        """Run a full, example silo workflow

The demo will create a silo named "Demo", add tables to it,
add random data, and then display that data via "tail".
        """
        from omero.rtypes import rstring, unwrap

        client = self.ctx.conn(args)
        us = client.sf.getUpdateService()
        qs = client.sf.getQueryService()

        self.ctx.out("\nExample silo session")
        self.ctx.out("="*80)

        commands = []
        commands.append(self._demo("List current silos", self.list))
        commands.append(self._demo("Create new silo", self.create, "Demo"))
        silo_id = self.ctx.get("rv")
        commands.append(self._demo("Re-list silos", self.list))

        commands.append(self._demo("Add audit log to silo %s" % silo_id, self.define, str(silo_id),\
            "AuditLog", "Long:user_id", "Long:timestamp", "String:resource:size=100", "String:action:size=100", "String:message:size=100"))

        commands.append(self._demo("Add user table to silo %s" % silo_id, self.define, str(silo_id),\
            "TypeA", "String:personal_id:size=12", "Long:measurement_1", "Long:measurement_2"))

        of = self.ctx.get("rv")
        self._demo("Add random data to table %s" % of.id.val)

        sr = client.sf.sharedResources()
        ot = sr.openTable(of)
        try:
            cs = ot.getHeaders()
            for c in cs:
                c.values = []
            for x in range(50):
                cs[0].values.append(("%s" % x) * 12)
                cs[1].values.append(x)
                cs[2].values.append(-x)
            ot.addData(cs)
        finally:
            ot.close()

        commands.append(self._demo("List tables attached to silo", self.tables, str(silo_id)))
        commands.append(self._demo("List last several lines of table %s" % of.id.val, self.tail, str(of.id.val)))
        commands.append(self._demo("List audit log", self.auditlog, str(silo_id)))
        commands.append(self._demo("List audit log again", self.auditlog, str(silo_id)))

        delete = self.ctx.controls["delete"]
        commands.append(delete._demo("Deleting silo %s" % silo_id, delete, "/OriginalFile:%s" % silo_id))
        commands.append(self._demo("List current silos", self.list))

        self.ctx.out("Summary of demo:")
        self.ctx.out("="*80)
        for command in commands:
            if command:
                print "omero", " ".join(command)

    def create(self, args):
        """Initializes a fresh silo"""

        import omero
        from omero.rtypes import rstring as _
        from omero.util.temp_files import create_path

        file = create_path()
        file.write_text(""" # Configuration
a = 1
b = 2
        """)
        client = self.ctx.conn(args)

        ofile = client.upload(filename = file.abspath(), path = "/Silos", name = args.name, type = "OMERO.silo")
        self.ctx.out("Saved %s as silo %s" % (file, ofile.id.val))
        self.ctx.set("rv", ofile.id.val)
        return ofile.id.val

    def define(self, args):
        """Define a new type in the silo"""

        from omero.grid import StringColumn, LongColumn
        from omero.model import OriginalFileI, FileAnnotationI, OriginalFileAnnotationLinkI
        from omero.rtypes import rstring, unwrap

        col_types = {"String": (StringColumn, {"size": int}), "Long": (LongColumn, dict())}

        client = self.ctx.conn(args)
        us = client.sf.getUpdateService()

        sr = client.sf.sharedResources()
        nt = sr.newTable(1, "/Silos/%s/%s" % (args.id, args.name))

        try:
            of = nt.getOriginalFile()
            self.ctx.out("Created table %s" % of.id.val)
            self.ctx.set("rv", of)

            fa = FileAnnotationI()
            fa.ns = rstring("openmicroscopy.org/silo/table")
            fa.file = of
            fl = OriginalFileAnnotationLinkI()
            fl.child = fa
            fl.parent = OriginalFileI(args.id, False)
            fl = us.saveAndReturnObject(fl)

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

            nt.initialize(cs)
            return of
        finally:
            nt.close()

    def auditlog(self, args):
        """Display audit log
        """
        table = self._auditlog(args.id)
        data = self._tail(table, table, 10)
        if data is None:
            self.ctx.die(101, "No audit logs")
        self.ctx.out(self._stringify(data))

    def list(self, args):
        """List available silos"""
        rv = self._query(LOAD_SILOS[0], 0, 10)
        self.ctx.out(self._stringify(rv, LOAD_SILOS[1]))

    def tables(self, args):
        """List tables associated with this silo"""
        rv = self._query(LOAD_TABLES[0] % args.id, 0, 10)
        self.ctx.out(self._stringify(rv, LOAD_TABLES[1]))

    def tail(self, args):
        """List the last several entries of the table"""

        client = self.ctx.conn(args)
        silo_id = self._silo_id(args.id)
        audit_log = self._auditlog(silo_id)
        try:
            table = self._open(args.id)
            try:
                data = self._tail(audit_log, table, args.count)
                if data is None:
                    self.ctx.die(101, "No data")
                self.ctx.out(self._stringify(data))
            finally:
                table.close()
        finally:
            audit_log.close()

    #
    # Helpers
    #
    def _auditlog(self, silo_id):
        """
        Load the single audit log for the given silo
        """
        logs = self._query(LOAD_AUDIT_LOG[0] % silo_id, 0, 10)

        if len(logs) != 1:
            self.ctx.die(100, "No single audit log found for silo %s! (size=%s)" % (silo_id, len(logs)))

        return self._open(logs[0][0])

    def _log(self, log, resource, action, message):
        cols = log.getHeaders()
        cols[0].values = [self.ctx._event_context.userId]
        cols[1].values = [long(time.time()*1000)]
        cols[2].values = [resource]
        cols[3].values = [action]
        cols[4].values = [message]
        log.addData(cols)

    def _open(self, id):
        from omero.model import OriginalFileI

        sr = self.ctx._client.sf.sharedResources()
        return sr.openTable(OriginalFileI(id, False))

    def _query(self, query, offset, limit):
        import omero
        from omero.rtypes import unwrap
        q = self.ctx._client.sf.getQueryService()
        p = omero.sys.ParametersI()
        p.page(offset, limit)
        rv = unwrap(q.projection(query, p))
        self.ctx.set("rv", rv)
        return rv

    def _silo_id(self, table_id):
        """
        Returns the unique silo id that this table id is attached to,
        or calls ctx.die otherwise.
        """
        rv = self._query(SILO_FROM_TABLE[0] % table_id, 0, 10)
        if len(rv) != 1:
            self.ctx.die(103, "Invalid number of silos for table %s: %s" % (table_id, len(rv)))
        return rv[0][0]

    def _tail(self, auditlog, table, count):
        """
        Return 'count' vailues from the end of table.
        If no fewer rows are present, then all rows
        are returned. If no rows are present, None is
        returned.
        """
        try:
            resource = "Table:%s" % table.getOriginalFile().id.val
            row_count = table.getNumberOfRows()
            if row_count == 0:
                return None

            if count > row_count:
                count = row_count

            rows = []
            for x in range(row_count - count, row_count, 1):
                rows.append(x)

            data = table.readCoordinates(rows)
            self.ctx.set("rv", data)
            self._log(auditlog, resource, "READ", "%s rows" % count)
        except:
            self._log(auditlog, resource, "FAILED_READ", "%s rows" % count)
            raise

        return data

    def _stringify(self, data, headers = None):
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
            tb = TableBuilder(*headers)
            for row in data:
                tb.row(*row)
        return tb

try:
    register("silo", SiloControl, HELP)
except NameError:
    import sys
    cli = CLI()
    cli.register("silo", SiloControl, HELP)
    cli.invoke(sys.argv[1:])
