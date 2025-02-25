#!/usr/bin/env python

"""
Python driver for OMERO

Provides access to various OMERO.blitz server- and client-side
utilities, including starting and stopping servers, running
analyses, configuration, and more.

Usable via the ./omero script provided with the distribution
as well as from python via "import omero.cli; omero.cli.argv()"

Arguments are taken from (in order of priority): the run method
arguments, sys.argv, and finally from standard-in using the
cmd.Cmd.cmdloop method.

Josh Moore, josh at glencoesoftware.com
Copyright (c) 2007, Glencoe Software, Inc.
See LICENSE for details.

"""

sys = __import__("sys")

import cmd, string, re, os, subprocess, socket, exceptions, traceback, glob, platform, time
import shlex
from exceptions import Exception as Exc
from threading import Thread, Lock
from path import path

from omero_ext.argparse import ArgumentError
from omero_ext.argparse import ArgumentParser
from omero_ext.argparse import FileType
from omero_ext.argparse import Namespace

# Help text
from omero_ext.argparse import ArgumentDefaultsHelpFormatter
from omero_ext.argparse import RawDescriptionHelpFormatter
from omero_ext.argparse import RawTextHelpFormatter
from omero_ext.argparse import SUPPRESS

from omero.util.concurrency import get_event
from omero.util.sessions import SessionsStore
from omero.util import get_user_dir

#
# Static setup
#

try:
    from omero_version import omero_version
    VERSION=omero_version
except ImportError:
    VERSION="Unknown" # Usually during testing

DEBUG = 0
if os.environ.has_key("DEBUG"):
    try:
        DEBUG = int(os.environ["DEBUG"])
    except ValueError:
        DEBUG = 1
    print "Deprecated warning: use the 'bin/omero --debug=x [args]' to debug"
    print "Running omero with debugging == 1"

OMERODOC = """
Command-line tool for local and remote interactions with OMERO.
"""
OMEROSHELL = """OMERO Python Shell. Version %s""" % str(VERSION)
OMEROHELP = """Type "help" for more information, "quit" or Ctrl-D to exit"""
OMEROSUBS = """Use %(prog)s <subcommand> -h for more information."""
OMEROSUBM = """<subcommand>"""
OMEROCLI = path(__file__).expand().dirname()
OMERODIR = os.getenv('OMERODIR', None)
if OMERODIR is not None:
    OMERODIR = path(OMERODIR)
else:
    OMERODIR = OMEROCLI.dirname().dirname().dirname()

COMMENT = re.compile("^\s*#")
RELFILE = re.compile("^\w")
LINEWSP = re.compile("^\s*\w+\s+")

#
# Possibilities:
#  - Always return and print any output
#  - Have a callback on the fired event
#  - how should state machine work?
#   -- is the last control stored somwhere? in a stack history[3]
#   -- or do they all share a central memory? self.ctx["MY_VARIABLE"]
#  - In almost all cases, mark a flag in the CLI "lastError" and continue,
#    allowing users to do something of the form: on_success or on_fail


#####################################################
#
# Exceptions
#
class NonZeroReturnCode(Exc):
    def __init__(self, rv, *args):
        self.rv = rv
        Exc.__init__(self, *args)


#####################################################
#

class HelpFormatter(RawTextHelpFormatter):
    """
    argparse.HelpFormatter subclass which cleans up our usage, preventing very long
    lines in subcommands.
    """

    def __init__(self, prog, indent_increment=2, max_help_position=40, width=None):
        RawTextHelpFormatter.__init__(self, prog, indent_increment, max_help_position, width)
        self._action_max_length = 20

    def _split_lines(self, text, width):
        return [text.splitlines()[0]]

    class _Section(RawTextHelpFormatter._Section):

        def __init__(self, formatter, parent, heading=None):
            #if heading:
            #    heading = "\n%s\n%s" % ("=" * 40, heading)
            RawTextHelpFormatter._Section.__init__(self, formatter, parent, heading)


class WriteOnceNamespace(Namespace):
    """
    Namespace subclass which prevents overwriting any values by accident.
    """
    def __setattr__(self, name, value):
        if hasattr(self, name):
            raise exceptions.Exception("%s already has field %s" % (self.__class__.__name__, name))
        else:
            return Namespace.__setattr__(self, name, value)


class Parser(ArgumentParser):
    """
    Extension of ArgumentParser for simplifying the
    _configure() code in most Controls
    """

    def __init__(self, *args, **kwargs):
        kwargs["formatter_class"] = HelpFormatter
        ArgumentParser.__init__(self, *args, **kwargs)
        self._positionals.title = "Positional Arguments"
        self._optionals.title = "Optional Arguments"
        self._optionals.description = "In addition to any higher level options"

    def sub(self):
        return self.add_subparsers(title = "Subcommands", description = OMEROSUBS, metavar = OMEROSUBM)

    def add(self, sub, func, help = None, **kwargs):
        if help is None:
            help = func.im_func.__doc__
        parser = sub.add_parser(func.im_func.__name__, help=help, description=help)
        parser.set_defaults(func=func, **kwargs)
        return parser

    def _check_value(self, action, value):
        # converted value must be one of the choices (if specified)
        if action.choices is not None and value not in action.choices:
            msg = 'invalid choice: %r\n\nchoose from:\n' % value
            choices = sorted(action.choices)
            msg += self._format_list(choices)
            raise ArgumentError(action, msg)

    def _format_list(self, choices):
            lines = ["\t"]
            if choices:
                while len(choices) > 1:
                    choice = choices.pop(0)
                    lines[-1] += ("%s, " % choice)
                    if len(lines[-1]) > 62:
                        lines.append("\t")
                lines[-1] += choices.pop(0)
            return "\n".join(lines)

class NewFileType(FileType):
    """
    Extension of the argparse.FileType to prevent
    overwrite existing files.
    """
    def __call__(self, string):
        if os.path.exists(string):
            raise ValueError("File exists: %s" % string)
        return FileType.__call__(self, string)


class DirectoryType(FileType):
    """
    Extension of the argparse.FileType to only allow
    existing directories.
    """
    def __call__(self, string):
        p = path(string)
        if not p.exists():
            raise ValueError("Directory does not exist: %s" % string)
        elif not p.isdir():
            raise ValueError("Path is not a directory: %s" % string)
        return str(p.abspath())


class ExceptionHandler(object):
    """
    Location for all logic which maps from server exceptions
    to specific states. This could likely be moved elsewhere
    for general client-side usage.
    """
    def is_constraint_violation(self, ve):
        if isinstance(ve, omero.ValidationException):
            if "org.hibernate.exception.ConstraintViolationException: could not insert" in str(ve):
                return True


class Context:
    """Simple context used for default logic. The CLI registry which registers
    the plugins installs itself as a fully functional Context.

    The Context class is designed to increase pluggability. Rather than
    making calls directly on other plugins directly, the pub() method
    routes messages to other commands. Similarly, out() and err() should
    be used for printing statements to the user, and die() should be
    used for exiting fatally.

    """

    def __init__(self, controls = None, params = None, prog = sys.argv[0]):
        self.controls = controls
        if self.controls is None:
            self.controls = {}
        self.params = params
        if self.params is None:
            self.params = {}
        self.event = get_event(name="CLI")
        self.dir = OMERODIR
        self.isdebug = DEBUG # This usage will go away and default will be False
        self.topics = {"debug":"""

        debug options for developers:

        The value to the debug argument is a comma-separated list of commands:

         * 'debug' prints at the "debug" level. Similar to setting DEBUG=1 in the environment.
         * 'trace' runs the command with tracing enabled.
         * 'profile' runs the command with profiling enabled.

        Only one of "trace" and "profile" can be chosen.

        Example:

            bin/omero --debug=debug,trace admin start # Debugs at level 1 and prints tracing
            bin/omero -d1 admin start                 # Debugs at level 1
            bin/omero -dp admin start                 # Prints profiling
            bin/omero -dt,p admin start               # Fails!; can't print tracing and profiling together
            bin/omero -d0 admin start                 # Disables debugging
        """}
        self.parser = Parser(prog = prog, description = OMERODOC)
        self.subparsers = self.parser_init(self.parser)

    def post_process(self):
        """
        Runs further processing once all the controls have been added.
        """
        sessions = self.controls["sessions"]

        login = self.subparsers.add_parser("login", help="Shortcut for 'sessions login'")
        login.set_defaults(func=lambda args:sessions.login(args))
        self.add_login(login)
        sessions._configure_login(login)

        logout = self.subparsers.add_parser("logout", help="Shortcut for 'sessions logout'")
        logout.set_defaults(func=lambda args:self.controls["sessions"].logout(args))

    def add_login(self, parser):
        parser.add_argument("-C", "--create", action="store_true", help="Create a new session regardless of existing ones")
        parser.add_argument("-s", "--server")
        parser.add_argument("-p", "--port")
        parser.add_argument("-g", "--group")
        parser.add_argument("-u", "--user")
        parser.add_argument("-w", "--password")
        parser.add_argument("-k", "--key", help="UUID of an active session")

    def parser_init(self, parser):
        parser.add_argument("-v", "--version", action="version", version="%%(prog)s %s" % VERSION)
        parser.add_argument("-d", "--debug", help="Use 'help debug' for more information", default = SUPPRESS)
        parser.add_argument("--path", help="Add file or directory to plugin list. Supports globs.", action = "append")
        self.add_login(parser)
        subparsers = parser.add_subparsers(title="Subcommands", description=OMEROSUBS, metavar=OMEROSUBM)
        return subparsers

    def get(self, key, defvalue = None):
        return self.params.get(key, defvalue)

    def set(self, key, value = True):
        self.params[key] = value

    def safePrint(self, text, stream, newline = True):
        """
        Prints text to a given string, caputring any exceptions.
        """
        try:
            stream.write(str(text) % {"program_name": sys.argv[0]})
            if newline:
                stream.write("\n")
            else:
                stream.flush()
        except:
            print >>sys.stderr, "Error printing text"
            print >>sys.stdout, text
            if self.isdebug:
                traceback.print_exc()

    def pythonpath(self):
        """
        Converts the current sys.path to a PYTHONPATH string
        to be used by plugins which must start a new process.

        Note: this was initially created for running during
        testing when PYTHONPATH is not properly set.
        """
        path = list(sys.path)
        for i in range(0,len(path)-1):
            if path[i] == '':
                path[i] = os.getcwd()
        pythonpath = ":".join(path)
        return pythonpath

    def userdir(self):
        """
        Returns a user directory (as path.path) which can be used
        for storing configuration. The directory is guaranteed to
        exist and be private (700) after execution.
        """
        dir = path(os.path.expanduser("~")) / "omero" / "cli"
        if not dir.exists():
            dir.mkdir()
        elif not dir.isdir():
            raise Exc("%s is not a directory"%dir)
        dir.chmod(0700)
        return dir

    def pub(self, args, strict = False):
        self.safePrint(str(args), sys.stdout)

    def input(self, prompt, hidden = False, required = False):
        """
        Reads from standard in. If hidden == True, then
        uses getpass
        """
        try:
            while True:
                if hidden:
                    import getpass
                    defuser = getpass.getuser()
                    rv = getpass.getpass(prompt)
                else:
                    rv = raw_input(prompt)
                if required and not rv:
                    self.out("Input required")
                    continue
                return rv
        except KeyboardInterrupt:
            self.die(1, "Cancelled")

    def out(self, text, newline = True):
        """
        Expects as single string as argument"
        """
        self.safePrint(text, sys.stdout, newline)

    def err(self, text, newline = True):
        """
        Expects a single string as argument.
        """
        self.safePrint(text, sys.stderr, newline)

    def dbg(self, text, newline = True, level = 1):
        """
        Passes text to err() if self.isdebug is set
        """
        if self.isdebug >= level:
            self.err(text, newline)

    def die(self, rc, args):
        raise exceptions.Exception((rc,args))

    def exit(self, args):
        self.out(args)
        self.interrupt_loop = True

    def call(self, args):
        self.out(str(args))

    def popen(self, args):
        self.out(str(args))

    def sleep(self, time):
        self.event.wait(time)

#####################################################
#
class BaseControl:
    """Controls get registered with a CLI instance on loadplugins().

    To create a new control, subclass BaseControl, implement _configure,
    and end your module with::

        try:
            register("name", MyControl, HELP)
        except:
            if __name__ == "__main__":
                cli = CLI()
                cli.register("name", MyControl, HELP)
                cli.invoke(sys.argv[1:])

    This module should be put in the omero.plugins package.

    All methods which do NOT begin with "_" are assumed to be accessible
    to CLI users.
    """

    ###############################################
    #
    # Mostly reusable code
    #
    def __init__(self, ctx = None, dir = OMERODIR, name = "UNKNOWN"):
        self.dir = path(dir) # Guaranteed to be a path
        self.ctx = ctx
        self._control_name = name
        if self.ctx is None:
            self.ctx = Context() # Prevents unncessary stop_event creation

    def _isWindows(self):
        p_s = platform.system()
        if p_s == 'Windows':
                return True
        else:
                return False

    def _host(self):
        """
        Return hostname of current machine. Termed to be the
        value return from socket.gethostname() up to the first
        decimal.
        """
        if not hasattr(self, "hostname") or not self.hostname:
            self.hostname = socket.gethostname()
            if self.hostname.find(".") > 0:
                self.hostname = self.hostname.split(".")[0]
        return self.hostname

    def _node(self, omero_node = None):
        """
        Return the name of this node, using either the environment
        vairable OMERO_NODE or _host(). Some subclasses may
        override this functionality, most notably "admin" commands
        which assume a node name of "master".

        If the optional argument is not None, then the OMERO_NODE
        environment variable will be set.
        """
        if omero_node != None:
                os.environ["OMERO_NODE"] = omero_node

        if os.environ.has_key("OMERO_NODE"):
            return os.environ["OMERO_NODE"]
        else:
            return self._host()

    def _icedata(self, property):
        """
        General data method for creating a path from an Ice property.
        """
        try:
            nodepath = self._properties()[property]

            if RELFILE.match(nodepath):
                nodedata = self.dir / path(nodepath)
            else:
                nodedata = path(nodepath)

            created = False
            if not nodedata.exists():
                self.ctx.out("Creating "+nodedata)
                nodedata.makedirs()
                created = True
            return (nodedata, created)

        except KeyError, ke:
            self.ctx.err(property + " is not configured")
            self.ctx.die(4, str(ke))

    def _initDir(self):
        """
        Initialize the directory into which the current node will log.
        """
        props = self._properties()
        nodedata = self._nodedata()
        logdata = self.dir / path(props["Ice.StdOut"]).dirname()
        if not logdata.exists():
            self.ctx.out("Initializing %s" % logdata)
            logdata.makedirs()


    def _nodedata(self):
        """
        Returns the data directory path for this node. This is determined
        from the "IceGrid.Node.Data" property in the _properties()
        map.

        The directory will be created if it does not exist.
        """
        data, created = self._icedata("IceGrid.Node.Data")
        return data

    def _regdata(self):
        """
        Returns the data directory for the IceGrid registry.
        This is determined from the "IceGrid.Registry.Data" property
        in the _properties() map.

        The directory will be created if it does not exist, and
        a warning issued.
        """
        data, created = self._icedata("IceGrid.Registry.Data")

    def _pid(self):
        """
        Returns a path of the form "_nodedata() / _node() + ".pid",
        i.e. a file named NODENAME.pid in the node's data directory.
        """
        pidfile = self._nodedata() / (self._node() + ".pid")
        return pidfile

    def _cfglist(self):
        """
        Returns a list of configuration files for this node. This
        defaults to the internal configuration for all nodes,
        followed by a file named NODENAME.cfg under the etc/
        directory, following by PLATFORM.cfg if it exists.
        """
        cfgs = self.dir / "etc"
        internal = cfgs / "internal.cfg"
        owncfg = cfgs / self._node() + ".cfg"
        results = [internal,owncfg]
        # Look for <platform>.cfg
        p_s = platform.system()
        p_c = cfgs / p_s + ".cfg"
        if p_c.exists():
            results.append(p_c)
        return results

    def _icecfg(self):
        """
        Uses _cfglist() to return a string argument of the form
        "--Ice.Config=..." suitable for passing to omero.client
        as an argument.
        """
        icecfg = "--Ice.Config=%s" % ",".join(self._cfglist())
        return str(icecfg)

    def _intcfg(self):
        """
        Returns an Ice.Config string with only the internal configuration
        file for connecting to the IceGrid Locator.
        """
        intcfg = self.dir / "etc" / "internal.cfg"
        intcfg.abspath()
        return str("--Ice.Config=%s" % intcfg)

    def _properties(self, prefix=""):
        """
        Loads all files returned by _cfglist() into a new
        Ice.Properties instance and return the map from
        getPropertiesForPrefix(prefix) where the default is
        to return all properties.
        """
        import Ice
        if getattr(self, "_props", None) is None:
            self._props = Ice.createProperties()
            for cfg in self._cfglist():
                try:
                    self._props.load(str(cfg))
                except Exc, exc:
                    self.ctx.die(3, "Could not find file: "+cfg + "\nDid you specify the proper node?")
        return self._props.getPropertiesForPrefix(prefix)

    def _ask_for_password(self, reason = "", root_pass = None, strict = True):
        while not root_pass or len(root_pass) < 1:
            root_pass = self.ctx.input("Please enter password%s: "%reason, hidden = True)
            if not strict:
                return root_pass
            if root_pass == None or root_pass == "":
                self.ctx.err("Password cannot be empty")
                continue
            confirm = self.ctx.input("Please re-enter password%s: "%reason, hidden = True)
            if root_pass != confirm:
                root_pass = None
                self.ctx.err("Passwords don't match")
                continue
            break
        return root_pass

    def _demo(self, title, method = None, *arguments):
        """
        Used during demos to print out statements.
        """
        indent = ""
        topbot = "-"

        self.ctx.out(indent + "+" + (topbot*68) + "+")
        title = indent + "| DESCRIPTION: %-53.53s | " % title
        self.ctx.out(title)
        if method == self:
            # Signifies that there are no subparsers
            cmd = indent + "| COMMAND: omero %-51.51s | " % ("%s %s" % (self._control_name, " ".join(arguments)))
            self.ctx.out(cmd)
        elif method :
            cmd = indent + "| COMMAND: omero %-51.51s | " % ("%s %s %s" % (self._control_name, method.__name__, " ".join(arguments)))
            self.ctx.out(cmd)
        self.ctx.out(indent + "+" + (topbot*68) + "+")
        self.ctx.out(" ")

        command = []
        try:
            if method == self:
                command = [self._control_name] + list(arguments)
                self.ctx.invoke(command)
            elif method:
                command = [self._control_name, method.__name__] + list(arguments)
                self.ctx.invoke(command)
        except exceptions.Exception, e:
            import traceback
            self.ctx.out("\nEXECUTION FAILED: %s" % e)
            self.ctx.dbg(traceback.format_exc())
        self.ctx.out("\n")
        return command

    ###############################################
    #
    # Methods likely to be implemented by subclasses
    #

    def _complete_file(self, f, dir = None):
        """
        f: path part
        """
        if dir is None:
            dir = self.dir
        else:
            dir = path(dir)
        p = path(f)
        if p.exists() and p.isdir():
            if not f.endswith(os.sep):
                return [p.basename()+os.sep]
            return [ str(x)[len(f):] for x in p.listdir() ]
        else:
            results = [ str(x.basename()) for x in dir.glob(f+"*")  ]
            if len(results) == 1:
                # Relative to cwd
                maybe_dir = path(results[0])
                if maybe_dir.exists() and maybe_dir.isdir():
                    return [ results[0] + os.sep ]
            return results

    def _complete(self, text, line, begidx, endidx):
        try:
            return self._complete2(text, line, begidx, endidx)
        except:
            self.ctx.dbg("Complete error: %s" % traceback.format_exc())

    def _complete2(self, text, line, begidx, endidx):
        items = shlex.split(line)
        parser = getattr(self, "parser", None)
        if parser:
            result = []
            actions = getattr(parser, "_actions")
            if actions:
                if len(items) > 1:
                    subparsers = [x for x in actions if x.__class__.__name__ == "_SubParsersAction"]
                    if subparsers:
                        subparsers = subparsers[0] # Guaranteed one
                        choice = subparsers.choices.get(items[-1])
                        if choice and choice._actions:
                            actions = choice._actions
                if len(items) > 2:
                    actions = [] # TBD

            for action in actions:
                if action.__class__.__name__ == "_HelpAction":
                    result.append("-h")
                elif action.__class__.__name__ == "_SubParsersAction":
                    result.extend(action.choices)

            return ["%s " % x for x in result if (not text or x.startswith(text)) and line.find(" %s " % x) < 0]

        # Fallback
        completions = [method for method in dir(self) if callable(getattr(self, method)) ]
        return [ str(method + " ") for method in completions if method.startswith(text) and not method.startswith("_") ]


class CLI(cmd.Cmd, Context):
    """
    Command line interface class. Supports various styles of executing the
    registered plugins. Each plugin is given the chance to update this class
    by adding methods of the form "do_<plugin name>".
    """

    class PluginsLoaded(object):
        """
        Thread-safe class for storing whether or not all the plugins
        have been loaded
        """
        def __init__(self):
            self.lock = Lock()
            self.done = False
        def get(self):
            self.lock.acquire()
            try:
                return self.done
            finally:
                self.lock.release()
        def set(self):
            self.lock.acquire()
            try:
                self.done = True
            finally:
                self.lock.release()

    def __init__(self, prog = sys.argv[0]):
        """
        Also sets the "_client" field for this instance to None. Each cli
        maintains a single active client. The "session" plugin is responsible
        for the loading of the client object.
        """
        cmd.Cmd.__init__(self)
        Context.__init__(self, prog = prog)
        self.prompt = 'omero> '
        self.interrupt_loop = False
        self.rv = 0                         #: Return value to be returned
        self._stack = []                    #: List of commands being processed
        self._client = None                 #: Single client for all activities
        self._plugin_paths = [OMEROCLI / "plugins"] #: Paths to be loaded; initially official plugins
        self._pluginsLoaded = CLI.PluginsLoaded()

    def default_config(self):
        from omero_ext.configobj import ConfigObj
        default_config = ConfigObj()
        default_config["sessions"] = {"log": "true"}
        return default_config

    def read_config(self, section, key, default = None):
        from omero_ext.configobj import ConfigObj
        default_config = self.default_config()

        dir = get_user_dir()
        if dir != None:
            ini = path(dir) / "omero" / "cli.ini"

        if ini is not None and ini.exists():
            self.dbg("Local settings: %s..." % ini)
            ini_config = ConfigObj(ini)
            default_config.merge(ini_config)

        try:
            val = default_config[section][key]
            self.dbg("Read config: %s.%s=%s" % (section, key, val))
        except KeyError:
            val = default
            self.dbg("Default config: %s.%s=%s" % (section, key, default))
        return val

    def write_config(self, section, key, value):

        dir = get_user_dir()
        if dir == None:
            return # Early exit!

        ini = path(dir) / "omero" / "cli.ini"
        from omero_ext.configobj import ConfigObj
        co = ConfigObj(infile = ini, create_empty = True)
        try:
            co[section][key] = value
        except KeyError:
            co[section] = {key: value}
        co.write()
        self.dbg("Wrote config: %s.%s=%s" % (section, key, value))

    def assertRC(self):
        if self.rv != 0:
            raise NonZeroReturnCode(self.rv, "assert failed")

    def invoke(self, line, strict = False, previous_args = None):
        """
        Copied from cmd.py
        """
        try:
            line = self.precmd(line)
            stop = self.onecmd(line, previous_args)
            stop = self.postcmd(stop, line)
            if strict:
                self.assertRC()
        finally:
            if len(self._stack) == 0:
                self.close()
            else:
                self.dbg("Delaying close for stack: %s" % len(self._stack), level = 2)

    def invokeloop(self):
        # First we add a few special commands to the loop
        class PWD(BaseControl):
            def __call__(self, args):
                    self.ctx.out(os.getcwd())
        class LS(BaseControl):
            def __call__(self, args):
                for p in sorted(path(os.getcwd()).listdir()):
                    self.ctx.out(str(p.basename()))
        class CD(BaseControl):
            def _complete(self, text, line, begidx, endidx):
                RE = re.compile("\s*cd\s*")
                m = RE.match(line)
                if m:
                    replaced = RE.sub('', line)
                    return self._complete_file(replaced, path(os.getcwd()))
                return []
            def _configure(self, parser):
                parser.set_defaults(func=self.__call__)
                parser.add_argument("dir", help = "Target directory")
            def __call__(self, args):
                os.chdir(args.dir)
        self.register("pwd", PWD, "Print the current directory")
        self.register("ls", LS, "Print files in the current directory")
        self.register("dir", LS, "Alias for 'ls'")
        self.register("cd", CD, "Change the current directory")

        try:
            self.selfintro = "\n".join([OMEROSHELL, OMEROHELP])
            if not self.stdin.isatty():
                self.selfintro = ""
                self.prompt = ""
            while not self.interrupt_loop:
                try:
                    # Calls the same thing as invoke
                    self.cmdloop(self.selfintro)
                except KeyboardInterrupt, ki:
                    self.selfintro = ""
                    self.out("Use quit to exit")
        finally:
            self.close()

    def postloop(self):
        # We've done the intro once now. Don't repeat yourself.
        self.selfintro = ""

    def onecmd(self, line, previous_args = None):
        """
        Single command logic. Overrides the cmd.Cmd logic
        by calling execute. Also handles various exception
        conditions.
        """
        try:
            # Starting a new command. Reset the return value to 0
            # If err or die are called, set rv non-0 value
            self.rv = 0
            try:
                self._stack.insert(0, line)
                self.dbg("Stack+: %s" % len(self._stack), level=2)
                self.execute(line, previous_args)
                return True
            finally:
                self._stack.pop(0)
                self.dbg("Stack-: %s" % len(self._stack), level=2)
        except SystemExit, exc: # Thrown by argparse
            self.dbg("SystemExit raised\n%s" % traceback.format_exc())
            self.rv = exc.code
            return False
        #
        # This was perhaps only needed previously
        # Omitting for the moment with the new
        # argparse refactoring
        #
        #except AttributeError, ae:
        #    self.err("Possible error in plugin:")
        #    self.err(str(ae))
        #    if self.isdebug:
        #        traceback.print_exc()
        except NonZeroReturnCode, nzrc:
            self.dbg(traceback.format_exc())
            self.rv = nzrc.rv
        return False # Continue

    def postcmd(self, stop, line):
        """
        Checks interrupt_loop for True and return as much
        which will end the call to cmdloop. Otherwise use
        the default postcmd logic (which simply returns stop)
        """
        if self.interrupt_loop:
            return True
        return cmd.Cmd.postcmd(self, stop, line)

    def execute(self, line, previous_args):
        """
        String/list handling as well as EOF and comment handling.
        Otherwise, parses the arguments as shlexed and runs the
        function returned by argparse.
        """

        if isinstance(line, (str, unicode)):
            if COMMENT.match(line):
                return # EARLY EXIT!
            args = shlex.split(line)
        elif isinstance(line, (tuple, list)):
            args = list(line)
        else:
            self.die(1, "Bad argument type: %s ('%s')" % (type(line), line))

        if not args:
            return
        elif args == ["EOF"]:
            self.exit("")
            return

        args = self.parser.parse_args(args, previous_args)
        args.prog = self.parser.prog
        self.waitForPlugins()

        debug_str = getattr(args, "debug", "")
        debug_opts = set([x.lower() for x in debug_str.split(",")])
        if "" in debug_opts:
            debug_opts.remove("")

        old_debug = self.isdebug
        if "debug" in debug_opts:
            self.isdebug = 1
            debug_opts.remove("debug")
        elif "0" in debug_opts:
            self.isdebug = 0
            debug_opts.remove("0")

        for x in range(1, 9):
            if str(x) in debug_opts:
                self.isdebug = x
                debug_opts.remove(str(x))

        try:
            if len(debug_opts) == 0:
                return args.func(args)
            elif len(debug_opts) > 1:
                self.die(9, "Conflicting debug options: %s" % ", ".join(debug_opts))
            elif "t" in debug_opts or "trace" in debug_opts:
                import trace
                tracer = trace.Trace()
                tracer.runfunc(args.func, args)
            elif "p" in debug_opts or "profile" in debug_opts:
                import hotshot
                from hotshot import stats
                prof = hotshot.Profile("hotshot_edi_stats")
                rv = prof.runcall( lambda: args.func(args) )
                prof.close()
                s = stats.load("hotshot_edi_stats")
                s.sort_stats("time").print_stats()
            else:
                self.die(10, "Unknown debug action: %s" % debug_opts)
        finally:
            self.isdebug = old_debug

    def completedefault(self, *args):
        return []

    def completenames(self, text, line, begidx, endidx):
        names = self.controls.keys()
        return [ str(n + " ") for n in names if n.startswith(line) ]

    ##########################################
    ##
    ## Context interface
    ##
    def exit(self, args, newline=True):
        self.out(args, newline)
        self.interrupt_loop = True

    def die(self, rc, text, newline=True):
        self.err(text, newline)
        self.rv = rc
        # self.interrupt_loop = True
        raise NonZeroReturnCode(rc, "die called: %s" % text)

    def _env(self):
        """
        Configure environment with PYTHONPATH as
        setup by bin/omero

        This list needs to be kept in line with OmeroPy/bin/omero

        """
        lpy = str(self.dir / "lib" / "python")
        ipy = str(self.dir / "lib" / "fallback")
        vlb = str(self.dir / "var" / "lib")
        paths = os.path.pathsep.join([lpy, vlb, ipy])

        env = dict(os.environ)
        pypath = env.get("PYTHONPATH", None)
        if pypath is None:
            pypath = paths
        else:
            if pypath.endswith(os.path.pathsep):
                pypath = "%s%s" % (pypath, paths)
            else:
                pypath = "%s%s%s" % (pypath, os.path.pathsep, paths)
        env["PYTHONPATH"] = pypath
        return env

    def _cwd(self, cwd):
        if cwd is None:
            cwd = str(OMERODIR)
        else:
            cwd = str(cwd)
        return cwd

    def call(self, args, strict = True, cwd = None):
        """
        Calls the string in a subprocess and dies if the return value is not 0
        """
        self.dbg("Executing: %s" % args)
        rv = subprocess.call(args, env = self._env(), cwd = self._cwd(cwd))
        if strict and not rv == 0:
            raise NonZeroReturnCode(rv, "%s => %d" % (" ".join(args), rv))
        return rv

    def popen(self, args, cwd = None, stdout = subprocess.PIPE, stderr = subprocess.PIPE, **kwargs):
        self.dbg("Returning popen: %s" % args)
        env = self._env()
        env.update(kwargs)
        return subprocess.Popen(args, env = env, cwd = self._cwd(cwd), stdout = stdout, stderr = stderr)

    def readDefaults(self):
        try:
            f = path(OMERODIR) / "etc" / "omero.properties"
            f = f.open()
            output = "".join(f.readlines())
            f.close()
        except:
            if self.isdebug:
                raise
            print "No omero.properties found"
            output = ""
        return output

    def parsePropertyFile(self, data, output):
        for line in output.splitlines():
            if line.startswith("Listening for transport dt_socket at address"):
                self.dbg("Ignoring stdout 'Listening for transport' from DEBUG=1")
                continue
            parts = line.split("=",1)
            if len(parts) == 2:
                data.properties.setProperty(parts[0],parts[1])
                self.dbg("Set property: %s=%s" % (parts[0],parts[1]) )
            else:
                self.dbg("Bad property:"+str(parts))
        return data

    def initData(self, properties=None):
        """
        Uses "omero prefs" to create an Ice.InitializationData().
        """

        if properties is None: properties = {}

        from omero.plugins.prefs import getprefs
        try:
            output = getprefs(["get"], str(OMERODIR / "lib"))
        except OSError, err:
            self.err("Error getting preferences")
            self.dbg(err)
            output = ""

        import Ice
        data = Ice.InitializationData()
        data.properties = Ice.createProperties()
        for k,v in properties.items():
            data.properties.setProperty(k,v)
        self.parsePropertyFile(data, output)
        return data

    def conn(self, args = None):
        """
        Returns any active _client object. If one is present but
        not alive, it will be removed.

        If no client is found and arguments are available,
        will use the current settings to connect.

        If required attributes are missing, will delegate to the login command.

        FIXME: Currently differing setting sessions on the same CLI instance
        will misuse a client.
        """
        if self._client:
            self.dbg("Found client")
            try:
                self._client.getSession().keepAlive(None)
                self.dbg("Using client")
                return self._client
            except KeyboardInterrupt:
                raise
            except exceptions.Exception, e:
                self.dbg("Removing client: %s" % e)
                self._client.closeSession()
                self._client = None

        if args is not None:
            self.controls["sessions"].login(args)

        return self._client # Possibly added by "login"

    def close(self):
        client = self._client
        if client:
            self.dbg("Closing client: %s" % client)
            client.__del__()

    ##
    ## Plugin registry
    ##

    def register(self, name, Control, help):
        self.register_only(name, Control, help)
        self.configure_plugins()

    def register_only(self, name, Control, help):
        """ This method is added to the globals when execfile() is
        called on each plugin. A Control class should be
        passed to the register method which will be added to the CLI.
        """
        self.controls[name] = (Control, help)

    def configure_plugins(self):
        """
        Run to instantiate and configure all plugins
        which were registered via register_only()
        """
        for name in sorted(self.controls):
            control = self.controls[name]
            if isinstance(control, tuple):
                Control = control[0]
                help = control[1]
                control = Control(ctx = self, dir = self.dir, name = name)
                self.controls[name] = control
                setattr(self, "complete_%s" % name, control._complete)
                parser = self.subparsers.add_parser(name, help=help)
                parser.description = help
                if hasattr(control, "_configure"):
                    control._configure(parser)
                elif hasattr(control, "__call__"):
                    parser.set_defaults(func=control.__call__)
                control.parser = parser

    def waitForPlugins(self):
        if True:
            return # Disabling. See comment in argv
        self.dbg("Starting waitForPlugins")
        while not self._pluginsLoaded.get():
            self.dbg("Waiting for plugins...")
            time.sleep(0.1)

    def loadplugins(self):
        """
        Finds all plugins and gives them a chance to register
        themselves with the CLI instance. Here register_only()
        is used to guarantee the orderedness of the plugins
        in the parser
        """

        for plugin_path in self._plugin_paths:
            self.loadpath(path(plugin_path))

        self.configure_plugins()
        self._pluginsLoaded.set()
        self.post_process()

    def loadpath(self, pathobj):
        if pathobj.isdir():
            for plugin in pathobj.walkfiles("*.py"):
                if -1 == plugin.find("#"): # Omit emacs files
                    self.loadpath(path(plugin))
        else:
            if self.isdebug:
                print "Loading %s" % pathobj
            try:
                loc = {"register": self.register_only}
                execfile( str(pathobj), loc )
            except KeyboardInterrupt:
                raise
            except:
                self.err("Error loading: %s" % pathobj)
                traceback.print_exc()

    ## End Cli
    ###########################################################

def argv(args=sys.argv):
    """
    Main entry point for the OMERO command-line interface. First
    loads all plugins by passing them the classes defined here
    so they can register their methods.

    Then the case where arguments are passed on the command line are
    handled.

    Finally, the cli enters a command loop reading from standard in.
    """

    # Modiying the run-time environment
    old_ice_config = os.getenv("ICE_CONFIG")
    os.unsetenv("ICE_CONFIG")
    try:

        # Modifying the args list if the name of the file
        # has arguments encoded in it
        original_executable = path(args[0])
        base_executable = str(original_executable.basename())
        if base_executable.find("-") >= 0:
            parts = base_executable.split("-")
            for arg in args[1:]:
                parts.append(arg)
            args = parts

        # Now load other plugins. After debugging is turned on, but before tracing.
        cli = CLI(prog = original_executable.split("-")[0])

        parser = Parser(add_help = False)
        #parser.add_argument("-d", "--debug", help="Use 'help debug' for more information", default = SUPPRESS)
        parser.add_argument("--path", help="Add file or directory to plugin list. Supports globs.", action = "append")
        ns, args = parser.parse_known_args(args)
        if getattr(ns, "path"):
            for p in ns.path:
                for g in glob.glob(p):
                    cli._plugin_paths.append(g)

        class PluginLoader(Thread):
            def run(self):
                cli.loadplugins()
	# Disabling background loading
	# until 2.4 hangs are fixed
        PluginLoader().run() # start()

        if len(args) > 1:
            cli.invoke(args[1:])
            return cli.rv
        else:
            cli.invokeloop()
            return cli.rv
    finally:
        if old_ice_config:
            os.putenv("ICE_CONFIG", old_ice_config)
