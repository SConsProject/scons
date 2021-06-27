# MIT License
#
# Copyright The SCons Foundation
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import collections
import unittest

import TestUnit

import SCons.compat
import SCons.Scanner

class DummyFS:
    def File(self, name):
        return DummyNode(name)

class DummyEnvironment(collections.UserDict):
    def __init__(self, mapping=None, **kwargs):
        super().__init__(mapping)
        self.data.update(kwargs)
        self.fs = DummyFS()
    def subst(self, strSubst, target=None, source=None, conv=None):
        if strSubst[0] == '$':
            return self.data[strSubst[1:]]
        return strSubst
    def subst_list(self, strSubst, target=None, source=None, conv=None):
        if strSubst[0] == '$':
            return [self.data[strSubst[1:]]]
        return [[strSubst]]
    def subst_path(self, path, target=None, source=None, conv=None):
        if not isinstance(path, list):
            path = [path]
        return list(map(self.subst, path))
    def get_factory(self, factory):
        return factory or self.fs.File

class DummyNode:
    def __init__(self, name, search_result=()):
        self.name = name
        self.search_result = tuple(search_result)
    def rexists(self):
        return 1
    def __str__(self):
        return self.name
    def Rfindalldirs(self, pathlist):
        return self.search_result + pathlist
    def __repr__(self):
        return self.name
    def __eq__(self, other):
        return self.name == other.name

class FindPathDirsTestCase(unittest.TestCase):
    def test_FindPathDirs(self):
        """Test the FindPathDirs callable class"""

        env = DummyEnvironment(LIBPATH = [ 'foo' ])
        env.fs = DummyFS()
        env.fs._cwd = DummyNode('cwd')

        dir = DummyNode('dir', ['xxx'])
        fpd = SCons.Scanner.FindPathDirs('LIBPATH')
        result = fpd(env)
        assert str(result) == "('foo',)", result
        result = fpd(env, dir)
        assert str(result) == "('xxx', 'foo')", result

class ScannerTestCase(unittest.TestCase):

    def test_creation(self):
        """Test creation of Scanner objects"""
        def func(self):
            pass
        s = SCons.Scanner.Base(func)
        assert isinstance(s, SCons.Scanner.Base), s
        s = SCons.Scanner.Base({})
        assert isinstance(s, SCons.Scanner.Base), s

        s = SCons.Scanner.Base(func, name='fooscan')
        assert str(s) == 'fooscan', str(s)
        s = SCons.Scanner.Base({}, name='barscan')
        assert str(s) == 'barscan', str(s)

        s = SCons.Scanner.Base(func, name='fooscan', argument=9)
        assert str(s) == 'fooscan', str(s)
        assert s.argument == 9, s.argument
        s = SCons.Scanner.Base({}, name='fooscan', argument=888)
        assert str(s) == 'fooscan', str(s)
        assert s.argument == 888, s.argument


class BaseTestCase(unittest.TestCase):

    class skey_node:
        def __init__(self, key):
            self.key = key
        def scanner_key(self):
            return self.key
        def rexists(self):
            return 1

    def func(self, filename, env, target, *args):
        self.filename = filename
        self.env = env
        self.target = target

        if len(args) > 0:
            self.arg = args[0]

        return self.deps

    def test(self, scanner, env, filename, deps, *args):
        self.deps = deps
        path = scanner.path(env)
        scanned = scanner(filename, env, path)
        scanned_strs = [str(x) for x in scanned]

        self.assertTrue(self.filename == filename, "the filename was passed incorrectly")
        self.assertTrue(self.env == env, "the environment was passed incorrectly")
        self.assertTrue(scanned_strs == deps, "the dependencies were returned incorrectly")
        for d in scanned:
            self.assertTrue(not isinstance(d, str), "got a string in the dependencies")

        if len(args) > 0:
            self.assertTrue(self.arg == args[0], "the argument was passed incorrectly")
        else:
            self.assertFalse(hasattr(self, "arg"), "an argument was given when it shouldn't have been")

    def test___call__dict(self):
        """Test calling Scanner.Base objects with a dictionary"""
        called = []
        def s1func(node, env, path, called=called):
            called.append('s1func')
            called.append(node)
            return []
        def s2func(node, env, path, called=called):
            called.append('s2func')
            called.append(node)
            return []
        s1 = SCons.Scanner.Base(s1func)
        s2 = SCons.Scanner.Base(s2func)
        selector = SCons.Scanner.Base({'.x' : s1, '.y' : s2})
        nx = self.skey_node('.x')
        env = DummyEnvironment()
        selector(nx, env, [])
        assert called == ['s1func', nx], called
        del called[:]
        ny = self.skey_node('.y')
        selector(ny, env, [])
        assert called == ['s2func', ny], called

    def test_path(self):
        """Test the Scanner.Base path() method"""
        def pf(env, cwd, target, source, argument=None):
            return "pf: %s %s %s %s %s" % \
                        (env.VARIABLE, cwd, target[0], source[0], argument)

        env = DummyEnvironment()
        env.VARIABLE = 'v1'
        target = DummyNode('target')
        source = DummyNode('source')

        s = SCons.Scanner.Base(self.func, path_function=pf)
        p = s.path(env, 'here', [target], [source])
        assert p == "pf: v1 here target source None", p

        s = SCons.Scanner.Base(self.func, path_function=pf, argument="xyz")
        p = s.path(env, 'here', [target], [source])
        assert p == "pf: v1 here target source xyz", p

    def test_positional(self):
        """Test the Scanner.Base class using positional arguments"""
        s = SCons.Scanner.Base(self.func, "Pos")
        env = DummyEnvironment()
        env.VARIABLE = "var1"
        self.test(s, env, DummyNode('f1.cpp'), ['f1.h', 'f1.hpp'])

        env = DummyEnvironment()
        env.VARIABLE = "i1"
        self.test(s, env, DummyNode('i1.cpp'), ['i1.h', 'i1.hpp'])

    def test_keywords(self):
        """Test the Scanner.Base class using keyword arguments"""
        s = SCons.Scanner.Base(function = self.func, name = "Key")
        env = DummyEnvironment()
        env.VARIABLE = "var2"
        self.test(s, env, DummyNode('f2.cpp'), ['f2.h', 'f2.hpp'])

        env = DummyEnvironment()
        env.VARIABLE = "i2"

        self.test(s, env, DummyNode('i2.cpp'), ['i2.h', 'i2.hpp'])

    def test_pos_opt(self):
        """Test the Scanner.Base class using both position and optional arguments"""
        arg = "this is the argument"
        s = SCons.Scanner.Base(self.func, "PosArg", arg)
        env = DummyEnvironment()
        env.VARIABLE = "var3"
        self.test(s, env, DummyNode('f3.cpp'), ['f3.h', 'f3.hpp'], arg)

        env = DummyEnvironment()
        env.VARIABLE = "i3"
        self.test(s, env, DummyNode('i3.cpp'), ['i3.h', 'i3.hpp'], arg)

    def test_key_opt(self):
        """Test the Scanner.Base class using both keyword and optional arguments"""
        arg = "this is another argument"
        s = SCons.Scanner.Base(function = self.func, name = "KeyArg",
                               argument = arg)
        env = DummyEnvironment()
        env.VARIABLE = "var4"
        self.test(s, env, DummyNode('f4.cpp'), ['f4.h', 'f4.hpp'], arg)

        env = DummyEnvironment()
        env.VARIABLE = "i4"
        self.test(s, env, DummyNode('i4.cpp'), ['i4.h', 'i4.hpp'], arg)

    def test___cmp__(self):
        """Test the Scanner.Base class __cmp__() method"""
        s = SCons.Scanner.Base(self.func, "Cmp")
        assert s is not None

    def test_hash(self):
        """Test the Scanner.Base class __hash__() method"""
        s = SCons.Scanner.Base(self.func, "Hash")
        mapping = {}
        mapping[s] = 777
        i = hash(id(s))
        h = hash(list(mapping)[0])
        self.assertTrue(h == i,
                        "hash Scanner base class expected %s, got %s" % (i, h))

    def test_scan_check(self):
        """Test the Scanner.Base class scan_check() method"""
        def my_scan(filename, env, target, *args):
            return []
        def check(node, env, s=self):
            s.checked[str(node)] = 1
            return 1
        env = DummyEnvironment()
        s = SCons.Scanner.Base(my_scan, "Check", scan_check = check)
        self.checked = {}
        path = s.path(env)
        scanned = s(DummyNode('x'), env, path)
        self.assertTrue(self.checked['x'] == 1,
                        "did not call check function")

    def test_recursive(self):
        """Test the Scanner.Base class recursive flag"""
        nodes = [1, 2, 3, 4]

        s = SCons.Scanner.Base(function = self.func)
        n = s.recurse_nodes(nodes)
        self.assertTrue(n == [],
                        "default behavior returned nodes: %s" % n)

        s = SCons.Scanner.Base(function = self.func, recursive = None)
        n = s.recurse_nodes(nodes)
        self.assertTrue(n == [],
                        "recursive = None returned nodes: %s" % n)

        s = SCons.Scanner.Base(function = self.func, recursive = 1)
        n = s.recurse_nodes(nodes)
        self.assertTrue(n == n,
                        "recursive = 1 didn't return all nodes: %s" % n)

        def odd_only(nodes):
            return [n for n in nodes if n % 2]
        s = SCons.Scanner.Base(function = self.func, recursive = odd_only)
        n = s.recurse_nodes(nodes)
        self.assertTrue(n == [1, 3],
                        "recursive = 1 didn't return all nodes: %s" % n)

    def test_get_skeys(self):
        """Test the Scanner.Base get_skeys() method"""
        s = SCons.Scanner.Base(function = self.func)
        sk = s.get_skeys()
        self.assertTrue(sk == [],
                        "did not initialize to expected []")

        s = SCons.Scanner.Base(function = self.func, skeys = ['.1', '.2'])
        sk = s.get_skeys()
        self.assertTrue(sk == ['.1', '.2'],
                        "sk was %s, not ['.1', '.2']")

        s = SCons.Scanner.Base(function = self.func, skeys = '$LIST')
        env = DummyEnvironment(LIST = ['.3', '.4'])
        sk = s.get_skeys(env)
        self.assertTrue(sk == ['.3', '.4'],
                        "sk was %s, not ['.3', '.4']")

    def test_select(self):
        """Test the Scanner.Base select() method"""
        scanner = SCons.Scanner.Base(function = self.func)
        s = scanner.select('.x')
        assert s is scanner, s

        selector = SCons.Scanner.Base({'.x' : 1, '.y' : 2})
        s = selector.select(self.skey_node('.x'))
        assert s == 1, s
        s = selector.select(self.skey_node('.y'))
        assert s == 2, s
        s = selector.select(self.skey_node('.z'))
        assert s is None, s

    def test_add_scanner(self):
        """Test the Scanner.Base add_scanner() method"""
        selector = SCons.Scanner.Base({'.x' : 1, '.y' : 2})
        s = selector.select(self.skey_node('.z'))
        assert s is None, s
        selector.add_scanner('.z', 3)
        s = selector.select(self.skey_node('.z'))
        assert s == 3, s

    def test___str__(self):
        """Test the Scanner.Base __str__() method"""
        scanner = SCons.Scanner.Base(function = self.func)
        s = str(scanner)
        assert s == 'NONE', s
        scanner = SCons.Scanner.Base(function = self.func, name = 'xyzzy')
        s = str(scanner)
        assert s == 'xyzzy', s

class SelectorTestCase(unittest.TestCase):
    class skey_node:
        def __init__(self, key):
            self.key = key
        def scanner_key(self):
            return self.key
        def rexists(self):
            return 1

    def test___init__(self):
        """Test creation of Scanner.Selector object"""
        s = SCons.Scanner.Selector({})
        assert isinstance(s, SCons.Scanner.Selector), s
        assert s.mapping == {}, s.mapping

    def test___call__(self):
        """Test calling Scanner.Selector objects"""
        called = []
        def s1func(node, env, path, called=called):
            called.append('s1func')
            called.append(node)
            return []
        def s2func(node, env, path, called=called):
            called.append('s2func')
            called.append(node)
            return []
        s1 = SCons.Scanner.Base(s1func)
        s2 = SCons.Scanner.Base(s2func)
        selector = SCons.Scanner.Selector({'.x' : s1, '.y' : s2})
        nx = self.skey_node('.x')
        env = DummyEnvironment()
        selector(nx, env, [])
        assert called == ['s1func', nx], called
        del called[:]
        ny = self.skey_node('.y')
        selector(ny, env, [])
        assert called == ['s2func', ny], called

    def test_select(self):
        """Test the Scanner.Selector select() method"""
        selector = SCons.Scanner.Selector({'.x' : 1, '.y' : 2})
        s = selector.select(self.skey_node('.x'))
        assert s == 1, s
        s = selector.select(self.skey_node('.y'))
        assert s == 2, s
        s = selector.select(self.skey_node('.z'))
        assert s is None, s

    def test_add_scanner(self):
        """Test the Scanner.Selector add_scanner() method"""
        selector = SCons.Scanner.Selector({'.x' : 1, '.y' : 2})
        s = selector.select(self.skey_node('.z'))
        assert s is None, s
        selector.add_scanner('.z', 3)
        s = selector.select(self.skey_node('.z'))
        assert s == 3, s

class CurrentTestCase(unittest.TestCase):
    def test_class(self):
        """Test the Scanner.Current class"""
        class MyNode:
            def __init__(self):
                self.called_has_builder = None
                self.called_is_up_to_date = None
                self.func_called = None
            def rexists(self):
                return 1
        class HasNoBuilder(MyNode):
            def has_builder(self):
                self.called_has_builder = 1
                return None
        class IsNotCurrent(MyNode):
            def has_builder(self):
                self.called_has_builder = 1
                return 1
            def is_up_to_date(self):
                self.called_is_up_to_date = 1
                return None
        class IsCurrent(MyNode):
            def has_builder(self):
                self.called_has_builder = 1
                return 1
            def is_up_to_date(self):
                self.called_is_up_to_date = 1
                return 1
        def func(node, env, path):
            node.func_called = 1
            return []
        env = DummyEnvironment()
        s = SCons.Scanner.Current(func)
        path = s.path(env)
        hnb = HasNoBuilder()
        s(hnb, env, path)
        self.assertTrue(hnb.called_has_builder, "did not call has_builder()")
        self.assertTrue(not hnb.called_is_up_to_date, "did call is_up_to_date()")
        self.assertTrue(hnb.func_called, "did not call func()")
        inc = IsNotCurrent()
        s(inc, env, path)
        self.assertTrue(inc.called_has_builder, "did not call has_builder()")
        self.assertTrue(inc.called_is_up_to_date, "did not call is_up_to_date()")
        self.assertTrue(not inc.func_called, "did call func()")
        ic = IsCurrent()
        s(ic, env, path)
        self.assertTrue(ic.called_has_builder, "did not call has_builder()")
        self.assertTrue(ic.called_is_up_to_date, "did not call is_up_to_date()")
        self.assertTrue(ic.func_called, "did not call func()")

class ClassicTestCase(unittest.TestCase):

    def func(self, filename, env, target, *args):
        self.filename = filename
        self.env = env
        self.target = target

        if len(args) > 0:
            self.arg = args[0]

        return self.deps

    def test_find_include(self):
        """Test the Scanner.Classic find_include() method"""
        env = DummyEnvironment()
        s = SCons.Scanner.Classic("t", ['.suf'], 'MYPATH', r'^my_inc (\S+)')

        def _find_file(filename, paths):
            return paths[0]+'/'+filename

        save = SCons.Node.FS.find_file
        SCons.Node.FS.find_file = _find_file

        try:
            n, i = s.find_include('aaa', 'foo', ('path',))
            assert n == 'foo/aaa', n
            assert i == 'aaa', i

        finally:
            SCons.Node.FS.find_file = save

    def test_name(self):
        """Test setting the Scanner.Classic name"""
        s = SCons.Scanner.Classic("my_name", ['.s'], 'MYPATH', r'^my_inc (\S+)')
        assert s.name == "my_name", s.name

    def test_scan(self):
        """Test the Scanner.Classic scan() method"""
        class MyNode:
            def __init__(self, name):
                self.name = name
                self._rfile = self
                self.includes = None
            def rfile(self):
                return self._rfile
            def exists(self):
                return self._exists
            def get_contents(self):
                return self._contents
            def get_text_contents(self):
                return self._contents
            def get_dir(self):
                return self._dir

        class MyScanner(SCons.Scanner.Classic):
            def find_include(self, include, source_dir, path):
                return include, include

        env = DummyEnvironment()
        s = MyScanner("t", ['.suf'], 'MYPATH', r'^my_inc (\S+)')

        # This set of tests is intended to test the scanning operation
        # of the Classic scanner.

        # Note that caching has been added for not just the includes
        # but the entire scan call.  The caching is based on the
        # arguments, so we will fiddle with the path parameter to
        # defeat this caching for the purposes of these tests.

        # If the node doesn't exist, scanning turns up nothing.
        n1 = MyNode("n1")
        n1._exists = None
        ret = s.function(n1, env)
        assert ret == [], ret

        # Verify that it finds includes from the contents.
        n = MyNode("n")
        n._exists = 1
        n._dir = MyNode("n._dir")
        n._contents = 'my_inc abc\n'
        ret = s.function(n, env, ('foo',))
        assert ret == ['abc'], ret

        # Verify that it uses the cached include info.
        n._contents = 'my_inc def\n'
        ret = s.function(n, env, ('foo2',))
        assert ret == ['abc'], ret

        # Verify that if we wipe the cache, it uses the new contents.
        n.includes = None
        ret = s.function(n, env, ('foo3',))
        assert ret == ['def'], ret

        # We no longer cache overall scan results, which would be returned
        # if individual results are de-cached.  If we ever restore that
        # functionality, this test goes back here.
        #ret = s.function(n, env, ('foo2',))
        #assert ret == ['abc'], 'caching inactive; got: %s'%ret

        # Verify that it sorts what it finds.
        n.includes = ['xyz', 'uvw']
        ret = s.function(n, env, ('foo4',))
        assert ret == ['uvw', 'xyz'], ret

        # Verify that we use the rfile() node.
        nr = MyNode("nr")
        nr._exists = 1
        nr._dir = MyNode("nr._dir")
        nr.includes = ['jkl', 'mno']
        n._rfile = nr
        ret = s.function(n, env, ('foo5',))
        assert ret == ['jkl', 'mno'], ret

    def test_recursive(self):
        """Test the Scanner.Classic class recursive flag"""
        nodes = [1, 2, 3, 4]


        s = SCons.Scanner.Classic("Test", [], None, "", function=self.func, recursive=1)
        n = s.recurse_nodes(nodes)
        self.assertTrue(n == n,
                        "recursive = 1 didn't return all nodes: %s" % n)

        def odd_only(nodes):
            return [n for n in nodes if n % 2]

        s = SCons.Scanner.Classic("Test", [], None, "", function=self.func, recursive=odd_only)
        n = s.recurse_nodes(nodes)
        self.assertTrue(n == [1, 3],
                        "recursive = 1 didn't return all nodes: %s" % n)


class ClassicCPPTestCase(unittest.TestCase):
    def test_find_include(self):
        """Test the Scanner.ClassicCPP find_include() method"""
        env = DummyEnvironment()
        s = SCons.Scanner.ClassicCPP("Test", [], None, "")

        def _find_file(filename, paths):
            return paths[0]+'/'+filename

        save = SCons.Node.FS.find_file
        SCons.Node.FS.find_file = _find_file

        try:
            n, i = s.find_include(('"', 'aaa'), 'foo', ('path',))
            assert n == 'foo/aaa', n
            assert i == 'aaa', i

            n, i = s.find_include(('<', 'bbb'), 'foo', ('path',))
            assert n == 'path/bbb', n
            assert i == 'bbb', i

            n, i = s.find_include(('<', 'ccc'), 'foo', ('path',))
            assert n == 'path/ccc', n
            assert i == 'ccc', i

        finally:
            SCons.Node.FS.find_file = save

def suite():
    suite = unittest.TestSuite()
    tclasses = [
                 FindPathDirsTestCase,
                 ScannerTestCase,
                 BaseTestCase,
                 SelectorTestCase,
                 CurrentTestCase,
                 ClassicTestCase,
                 ClassicCPPTestCase,
               ]
    for tclass in tclasses:
        names = unittest.getTestCaseNames(tclass, 'test_')
        suite.addTests(list(map(tclass, names)))
    return suite

if __name__ == "__main__":
    TestUnit.run(suite())

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
