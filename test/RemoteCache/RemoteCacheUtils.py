#!/usr/bin/env python
#
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
#

"""
Test utilities shared between remote cache tests.
"""

import atexit
import os
import random
import subprocess
import sys


def start_test_server(directory):
    """
    Starts a test script which pretends to be a Bazel remote cache server
    Returns the full url to the test server, which should be passed into SCons
    using --remote-cache-url
    """
    host = 'localhost'
    port = str(random.randint(49152, 65535))
    process = subprocess.Popen(
        [sys.executable,
         os.path.join(os.path.dirname(__file__), 'RemoteCacheTestServer.py'),
         host, port],
        cwd=directory, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def ShutdownServer():
        process.kill()
    atexit.register(ShutdownServer)

    return 'http://%s:%s' % (host, port)


def skip_test_if_no_urllib3(test):
    """Skips the test if urllib3 is not available"""
    try:
        import urllib3  # noqa: F401
    except ImportError:
        test.skip_test('urllib3 not found; skipping test')
