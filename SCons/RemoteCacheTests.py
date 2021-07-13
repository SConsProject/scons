# MIT License
#
# Copyright 2020 VMware, Inc.
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

from hashlib import sha256
import json
import os
import queue
import stat
import unittest
from unittest import mock

import TestSCons

import SCons.RemoteCache

# If the Python version running the tests doesn't have urllib3, then
# RemoteCache.py will not have the urllib3 attribute. However, the various
# mock.patch decorators below depend upon the attribute existing.
if not hasattr(SCons.RemoteCache, 'urllib3'):
    SCons.RemoteCache.urllib3 = None


class Url():
    """Test version of the urllib3's Url class."""
    __slots__ = ['host', 'scheme', 'port', 'path']

    def __init__(self):
        self.host = None
        self.scheme = None
        self.port = 0
        self.path = None


def MockParseUrl(address):
    """Naive implementation of URL parsing. Just enough for tests."""
    url = Url()
    components = address.split('://', 1)
    if len(components) > 1:
        if components[0]:
            url.scheme = components[0]
        else:
            # Invalid URL starting with ://
            return None

    components = components[-1].split('/', 1)
    port_components = components[0].split(':', 1)
    url.host = port_components[0]
    if len(port_components) > 1:
        url.port = int(port_components[1])
    else:
        url.port = 443 if url.scheme == 'https' else 80
    if len(components) > 1:
        url.path = components[1]
    return url


class MockResponse(mock.MagicMock):
    """Mock version of a response class that comes from urllib3.response."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for key, val in kwargs.items():
            setattr(self, key, val)

class MockConnectionPool(mock.MagicMock):
    """Mock version of the urllib3.ConnectionPool class."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.pending_responses = []

    def add_pending_response(self, **kwargs):
        self.pending_responses.append(MockResponse(**kwargs))

    def request(self, verb, url, *args, **kwargs):
        return self.pending_responses.pop(0)

    def urlopen(self, verb, url, *args, **kwargs):
        return self.pending_responses.pop(0)


def MockConnectionFromUrl(*args, **kwargs):
    """
    Mock side effect for function urllib3.ConnectionPool.connection_from_url.
    Returns a mock version of urllib3.ConnectionPool.
    """
    return MockConnectionPool(*args, **kwargs)


class Task():
    """Test version of the Task class."""
    slots = ['targets', 'cacheable']

    def __init__(self, targets, cacheable):
        self.targets = targets
        self.cacheable = cacheable

    def is_cacheable(self):
        return self.cacheable


def CreateRemoteCache(mock_urllib3, worker_count, server_address,
                      fetch_enabled, push_enabled):
    """
    Creates an instance of the RemoteCache class using various mock classes.
    """
    # Initialize all mocks.
    mock_urllib3.util.parse_url = mock.MagicMock(side_effect=MockParseUrl)
    mock_urllib3.connectionpool.connection_from_url = mock.MagicMock(
        side_effect=MockConnectionFromUrl)

    # Create the remote cache and queue.
    cache = SCons.RemoteCache.RemoteCache(
        worker_count, server_address, fetch_enabled, push_enabled, None)
    mock_urllib3.util.parse_url.assert_called_with(server_address)
    assert cache is not None, cache
    q = queue.Queue(0)
    cache.set_fetch_response_queue(q)

    return cache, q


def GetJSONMetadata(files):
    """
    Retrieves the JSON metadata for the specified files. Files can either be a
    single tuple or a list of tuples. Each tuple should have the following:

    1. Filename.
    2. Contents.
    3. Hash.
    4. (Optional) True if the file is executable on posix. Default is False.
    """
    if isinstance(files, tuple):
        files = [files]

    output_files = []
    for file in files:
        if len(file) == 4:
            (filename, contents, hash, isExecutable) = file
        else:
            (filename, contents, hash) = file
            isExecutable = False

        output_file = {
            'path': filename,
            'digest': {
                'hash': hash,
                'sizeBytes': len(contents),
            },
        }
        if os.name == 'posix':
            output_file['isExecutable'] = isExecutable
        output_files.append(output_file)

    return json.dumps({'outputFiles': output_files}).encode()


class TestCaseBase(unittest.TestCase):
    """Base test case that does common test setup."""
    def setUp(self):
        SCons.Util.set_hash_format('sha256')
        self.test = TestSCons.TestSCons()
        self.env = self.test.Environment()
        self.name = self.__class__.__name__


class FetchOneTargetTestCase(TestCaseBase):
    """Fetches one task from cache."""
    @mock.patch('SCons.RemoteCache.urllib3')
    def runTest(self, mock_urllib3):
        cache, q = CreateRemoteCache(mock_urllib3, 4, 'test', True, False)

        # Test making a request.
        contents = b'a'
        hash = sha256(contents).hexdigest()
        data = GetJSONMetadata((self.name, contents, hash))
        cache.connection_pool.add_pending_response(status=200, data=data)
        cache.connection_pool.add_pending_response(status=200, data=contents)

        t = self.env.File(self.name)
        task = Task([t], True)
        fetch_result = cache.fetch_task(task)
        assert fetch_result == (True, True), fetch_result

        task2, hit, target_infos = q.get()
        assert task == task2
        assert t.cached
        assert t.get_contents() == contents, t.get_contents()
        assert t.get_csig() == hash, t.get_csig()
        assert hit
        assert target_infos == [(hash, len(contents))]
        assert not cache.connection_pool.pending_responses, \
            cache.connection_pool.pending_responses


class FetchMultipleTargetsTestCase(TestCaseBase):
    """
    Tests fetching a task with multiple targets. This will result in /ac/ fetch
    and multiple /cas/ fetches.
    """
    @mock.patch('SCons.RemoteCache.urllib3')
    def runTest(self, mock_urllib3):
        cache, q = CreateRemoteCache(mock_urllib3, 4, 'test', True, False)

        # Test making a request.
        filename1 = self.name
        contents1 = b'a'
        filename2 = filename1 + '2'
        contents2 = b'b'
        hash1 = sha256(contents1).hexdigest()
        hash2 = sha256(contents2).hexdigest()
        data = GetJSONMetadata([(filename1, contents1, hash1),
                                (filename2, contents2, hash2)])
        cache.connection_pool.add_pending_response(status=200, data=data)
        cache.connection_pool.add_pending_response(status=200, data=contents1)
        cache.connection_pool.add_pending_response(status=200, data=contents2)

        t1 = self.env.File(filename1)
        t2 = self.env.File(filename2)
        task = Task([t1, t2], True)
        fetch_result = cache.fetch_task(task)
        assert fetch_result == (True, True), fetch_result

        task2, hit, target_infos = q.get()
        assert task == task2
        assert t1.cached
        assert t1.get_contents() == contents1, t1.get_contents()
        assert t1.get_csig() == hash1, t1.get_csig()
        assert t2.cached
        assert t2.get_contents() == contents2, t2.get_contents()
        assert t2.get_csig() == hash2, t2.get_csig()
        assert hit
        assert target_infos == [(hash1, len(contents1)),
                                (hash2, len(contents2))]
        assert not cache.connection_pool.pending_responses, \
            cache.connection_pool.pending_responses


class PushMultipleTargetsTestCase(TestCaseBase):
    """
    Tests pushing a task with multiple targets. This will result in /cas/
    pushes and one /ac/ push.
    """
    @mock.patch('SCons.RemoteCache.urllib3')
    def runTest(self, mock_urllib3):
        cache, q = CreateRemoteCache(mock_urllib3, 4, 'test', False, True)

        # Push two targets. If it's a posix machine, mark one of them as
        # executable.
        targets = []
        file_infos = [(self.name, b'a', sha256(b'a').hexdigest(), True),
                      (self.name + '2', b'b', sha256(b'b').hexdigest(), False)]
        for name, contents, _, executable in file_infos:
            t = self.env.File(name)
            with open(t.abspath, 'w') as f:
                f.write(contents.decode())

            if os.name == 'posix' and executable:
                self.env.fs.chmod(
                    t.abspath,
                    stat.S_IXUSR | self.env.fs.stat(t.abspath)[stat.ST_MODE])

            targets.append(t)

        data = GetJSONMetadata(file_infos)
        cache.connection_pool.add_pending_response(status=200, data=file_infos[0][1])
        cache.connection_pool.add_pending_response(status=200, data=file_infos[1][1])
        cache.connection_pool.add_pending_response(status=200, data=data)

        task = Task(targets, True)
        cache.push_task(task)
        connection_pool = cache.connection_pool
        cache.close()  # This will wait for ThreadPool requests to complete.
        assert not connection_pool.pending_responses, \
            connection_pool.pending_responses


class FetchMetadataFailureTestCase(TestCaseBase):
    """Tests a failed /ac/ request."""
    @mock.patch('SCons.RemoteCache.urllib3')
    def runTest(self, mock_urllib3):
        cache, q = CreateRemoteCache(mock_urllib3, 4, 'test', True, False)

        cache.connection_pool.add_pending_response(status=404)

        t = self.env.File(self.name)
        task = Task([t], True)
        fetch_result = cache.fetch_task(task)
        assert fetch_result == (True, True), fetch_result

        task2, hit, target_infos = q.get()
        assert task == task2
        assert not t.cached
        assert not hit
        assert target_infos is None
        assert not cache.connection_pool.pending_responses, \
            cache.connection_pool.pending_responses


class FetchNodeContentsFailureTestCase(TestCaseBase):
    """Tests a successful /ac/ request but failed /cas/ request."""
    @mock.patch('SCons.RemoteCache.urllib3')
    def runTest(self, mock_urllib3):
        cache, q = CreateRemoteCache(mock_urllib3, 4, 'test', True, False)

        contents = b'a'
        hash = sha256(contents).hexdigest()
        data = GetJSONMetadata((self.name, contents, hash))
        cache.connection_pool.add_pending_response(status=200, data=data)
        cache.connection_pool.add_pending_response(status=404)

        t = self.env.File(self.name)
        task = Task([t], True)
        fetch_result = cache.fetch_task(task)
        assert fetch_result == (True, True), fetch_result

        task2, hit, target_infos = q.get()
        assert task == task2
        assert not t.cached
        assert not hit
        assert target_infos is None
        assert not cache.connection_pool.pending_responses, \
            cache.connection_pool.pending_responses


if __name__ == "__main__":
    unittest.main()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
