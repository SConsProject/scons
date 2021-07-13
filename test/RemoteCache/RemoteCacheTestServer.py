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
RemoteCacheTestServer.py

Test Python script that acts like a Bazel remote cache server.
"""

import argparse
import hashlib
import http.server
import os

parser = argparse.ArgumentParser(
    description='Test loopback remote cache server')
parser.add_argument('address', help='Address to listen on')
parser.add_argument('port', type=int, help='Port to listen on')
args = vars(parser.parse_args())


class HandlerClass(http.server.SimpleHTTPRequestHandler):
    """
    Subclass of SimpleHTTPRequestHandler to handle PUT and GET requests, which
    are the only requests that the SCons remote caching code makes.
    SimpleHTTPRequestHandler automatically supports GET requests, so we only
    need to implement PUT requests. http.client has code to handle a request
    XYZ by calling the do_XYZ function, so we only need to implement do_PUT.
    """
    def do_PUT(self):
        path = self.translate_path(self.path)
        dir, file = os.path.split(path)
        if not os.path.exists(dir):
            os.makedirs(dir)

        length = int(self.headers['Content-Length'])
        data = self.rfile.read(length)

        if os.path.basename(dir) == 'cas':
            # For Content Addressable Storage entries, validate that the last
            # path segment matches the sha256 of the content; return
            # Unprocessable Entity otherwise.
            actual_sha256 = hashlib.sha256(data).hexdigest()
            if file != actual_sha256:
                self.send_response(422)
                self.end_headers()
                return

        with open(path, 'wb') as f:
            f.write(data)

        # No Content is a standard answer for a successful resource PUT.
        self.send_response(204)
        self.end_headers()

with http.server.HTTPServer((args['address'], args['port']),
                            HandlerClass) as httpd:
    httpd.serve_forever()
