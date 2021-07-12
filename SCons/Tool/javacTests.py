#
# __COPYRIGHT__
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
#

import os
import unittest

import SCons.Tool.javac

class DummyNode:
    def __init__(self, val):
        self.val = val

    def __str__(self):
        return str(self.val)

class pathoptTestCase(unittest.TestCase):
    def assert_pathopt(self, expect, path):
        popt = SCons.Tool.javac.pathopt('-foopath', 'FOOPATH')
        env = {'FOOPATH': path}
        actual = popt(None, None, env, None)
        self.assertEqual(expect, actual)

    def assert_pathopt_default(self, expect, path, default):
        popt = SCons.Tool.javac.pathopt('-foopath', 'FOOPATH', default='DPATH')
        env = {'FOOPATH': path,
               'DPATH': default}
        actual = popt(None, None, env, None)
        self.assertEqual(expect, actual)

    def test_unset(self):
        self.assert_pathopt([], None)
        self.assert_pathopt([], '')

    def test_str(self):
        self.assert_pathopt(['-foopath', '/foo/bar'],
                            '/foo/bar')

    def test_list_str(self):
        self.assert_pathopt(['-foopath', '/foo%s/bar' % os.pathsep],
                            ['/foo', '/bar'])

    def test_uses_pathsep(self):
        save = os.pathsep
        try:
            os.pathsep = '!'
            self.assert_pathopt(['-foopath', 'foo!bar'],
                                ['foo', 'bar'])
        finally:
            os.pathsep = save

    def test_node(self):
        self.assert_pathopt(['-foopath', '/foo'],
                            DummyNode('/foo'))

    def test_list_node(self):
        self.assert_pathopt(['-foopath', os.pathsep.join(['/foo','/bar'])],
                            ['/foo', DummyNode('/bar')])

    def test_default_str(self):
        self.assert_pathopt_default(
            ['-foopath', os.pathsep.join(['/foo','/bar','/baz'])],
            ['/foo', '/bar'],
            '/baz')

    def test_default_list(self):
        self.assert_pathopt_default(
            ['-foopath', os.pathsep.join(['/foo','/bar','/baz'])],
            ['/foo', '/bar'],
            ['/baz'])

    def test_default_unset(self):
        self.assert_pathopt_default(
            ['-foopath', '/foo'],
            '/foo',
            None)
        self.assert_pathopt_default(
            ['-foopath', '/foo'],
            '/foo',
            '')
    
    def test_list_within_list(self):
        self.assert_pathopt(['-foopath', os.pathsep.join(['/foo','/bar'])],
                    ['/foo', ['/bar']])


if __name__ == "__main__":
    unittest.main()
