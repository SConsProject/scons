"""SCons.RemoteCache

This class owns the logic related to pushing to and fetching from a Bazel
remote cache server. That server stores Task metadata in the /ac/ section
(action cache) and Node binary data in the /cas/ section (content-addressible
storage).

The Bazel remote cache uses LRU cache eviction for binaries in the
content-addressible storage. This means that Task metadata could exist in the
action cache /ac/ section but one or more of the Node binary data could be
missing due to eviction. Thus, in order for a Task to be fulfilled from cache,
we must verify that the Task metadata exists in the action cache and all Node
binary data exists in the content-addressible storage.

This class can be configured to do cache fetch, cache push, or both.

The first step of fetching a  Task is to issue a GET request to the /ac/
portion of the Bazel remote cache server. The server does validation of the
/ac/ request so it should only succeed if (1) the record exists on the server
and (2) the /cas/ storage has not evicted the nodes.

We use two ThreadPoolExecutor instances. The first instance is responsible for
fetching a task from cache; a request to that executor is done when an entire
task fetch is completed, either resulting in a cache hit or cache miss. The
second instance is response for singular network accesses; a request to that
executor is done when the specified network request is completed.

The second ThreadPoolExecutor is needed because the urllib3 API is synchronous
and we want multi-target tasks to be fetched in parallel. Requests to the first
ThreadPoolExecutor will wait on requests to the second ThreadPoolExecutor. If
we only used the one ThreadPoolExecutor and that executor was full of task
fetch requests, the cache would hang because there would be no room for the
individual network requests. We avoid that starvation by using the second
ThreadPoolExecutor.

For security purposes and due to requirements by the Bazel remote cache server,
/ac/ and /cas/ requests always use SHA-256. This requires that SCons uses
SHA-256 content signatures. The security reasons are primarily to avoid
collisions with other actions.

"""

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

__revision__ = "__FILE__ __REVISION__ __DATE__ __DEVELOPER__"

import SCons.Node.FS
import SCons.Script
import SCons.Util

from concurrent.futures import ThreadPoolExecutor

import datetime
import json
import os
import queue
import random
import stat
import sys
import time
import threading

try:
    import urllib3
    urllib3_exception = None
except ImportError as e:
    urllib3_exception = e


def raise_if_not_supported():
    # Verify that all required packages are present.
    if urllib3_exception:
        raise SCons.Errors.UserError(
            'Remote caching was requested but it is not supported in this '
            'deployment. urllib3 is required but missing: %s' %
            urllib3_exception)


class RemoteCache(object):
    __slots__ = [
        'backoff_remission_sec',
        'cache_ok_since',
        'connection_pool',
        'current_reset_backoff_multiplier',
        'debug_file',
        'failure_count',
        'fetch_enabled',
        'fetch_enabled_currently',
        'fetch_response_queue',
        'fs',
        'executor',
        'log',
        'metadata_request_timeout_sec',
        'metadata_version',
        'os_platform',
        'push_enabled',
        'push_enabled_currently',
        'request_executor',
        'request_failure_threshold',
        'reset_backoff_multiplier',
        'reset_count',
        'reset_delay_sec',
        'reset_skew_sec',
        'server_address',
        'server_path',
        'sessions',
        'stats_download_requests',
        'stats_download_total_bytes',
        'stats_download_total_ms',
        'stats_metadata_requests',
        'stats_metadata_total_ms',
        'stats_upload_requests',
        'stats_upload_total_bytes',
        'stats_upload_total_ms',
        'stats_lock',
        'total_failure_count',
        'transfer_request_timeout_sec'
    ]

    def __init__(self, worker_count, server_address, fetch_enabled,
                 push_enabled, cache_debug):
        """
        Initializes the cache. Supported parameters:
            worker_count: Number of threads to create.
            server_address: URL of remote server. Only the server name is
                            required, but the following can also be provided:
                            scheme, port, and url.
            fetch_enabled: True if fetch is enabled.
            push_enabled: True if push is enabled.
            cache_debug: File to debug log to, '-' for stdout, None otherwise.
        """
        self.debug_file = None
        self.sessions = {}
        self.fetch_enabled = fetch_enabled
        self.push_enabled = push_enabled
        self.log = SCons.Util.display
        self.fs = SCons.Node.FS.default_fs  # TODO: Use something better?
        self.fetch_response_queue = None
        self.failure_count = 0
        self.total_failure_count = 0
        self.cache_ok_since = 0.0
        self.reset_count = 0
        self.fetch_enabled_currently = self.fetch_enabled
        self.push_enabled_currently = self.push_enabled
        self.current_reset_backoff_multiplier = 1.0
        self.stats_lock = threading.Lock()
        self.stats_download_requests = 0
        self.stats_download_total_bytes = 0
        self.stats_download_total_ms = 0
        self.stats_metadata_requests = 0
        self.stats_metadata_total_ms = 0
        self.stats_upload_requests = 0
        self.stats_upload_total_bytes = 0
        self.stats_upload_total_ms = 0

        if cache_debug == '-':
            self.debug_file = sys.stdout
        elif cache_debug:
            try:
                self.debug_file = open(cache_debug, 'w')
            except Exception as e:
                self.log('WARNING: Unable to open cache debug file "%s" for '
                         'write with exception: %s.' % (cache_debug, e))

        # This is hardcoded and expected to change if we ever change the
        # contents of _get_task_metadata_signature. That allows us to
        # continue to add more contents to the metadata over time and
        # put it in a different place in the /ac/ section of the remote
        # cache.
        self.metadata_version = 1

        # Include the platform in the signature. This is for the case where
        # we have python actions that behave differently based on OS (so
        # simply hashing the code isn't enough).
        #
        # Note: before python 3.3, 'linux2' was returned for linux kernels
        #       >2.6. Now it's just 'linux'. Other platforms (FreeBSD, etc)
        #       have also added version numbers. For our uses, we just strip
        #       them all. As a side effect, 'win32' becomes 'win'.
        self.os_platform = sys.platform.rstrip('0123456789')

        # Maximum number of failures that we allow before disabling remote
        # caching.
        self.request_failure_threshold = 10

        # Per-request timeouts. The first is for /ac/. The second is for /cas/.
        self.metadata_request_timeout_sec = 10
        self.transfer_request_timeout_sec = 120  # 2 min

        # Time until we attempt a cache restart (+/- skew)
        self.reset_delay_sec = 240.0  # 4 min
        self.reset_skew_sec = 60.0  # 1 min

        # Exponential backoff multiplier
        self.reset_backoff_multiplier = 1.5

        # Time without errors before exponential backoff resets
        self.backoff_remission_sec = 180.0  # 3 min

        # Generate the server address using the passed in data.
        url_info = urllib3.util.parse_url(server_address)
        if not url_info or not url_info.host:
            raise SCons.Errors.UserError('An invalid remote cache server URL '
                                         '"%s" was provided' % server_address)
        elif (url_info.scheme and
                url_info.scheme.lower() not in ['http', 'https']):
            raise SCons.Errors.UserError('Remote cache server URL must '
                                         'start with http:// or https://')
        self.server_address = '%s://%s' % (
            url_info.scheme if url_info.scheme else 'http', url_info.host)
        if url_info.port:
            self.server_address = '%s:%d' % (self.server_address,
                                             url_info.port)

        # It is also allowable for the URL to contain a path, to which /ac/ and
        # /cas/ requests should be appended.
        self.server_path = url_info.path.rstrip('/') if url_info.path else ''

        # Create the thread pool and the connection pool that it uses.
        # Have urllib3 perform 1 retry per request (its default is 3). 1 retry
        # is helpful if in case of an unstable WiFi connection, while not
        # taking too long to fail if the server is unreachable.
        self.executor = ThreadPoolExecutor(max_workers=worker_count)
        self.connection_pool = urllib3.connectionpool.connection_from_url(
            self.server_address, maxsize=worker_count, block=True,
            retries=1)
        self.request_executor = ThreadPoolExecutor(max_workers=worker_count)

        self._debug('Remote cache server is configured as %s and max '
                    'connection count is %d.' %
                    (self.server_address + self.server_path, worker_count))

    def _get_node_data_url(self, csig):
        """Retrieves the URL for the specified node."""
        return '%s/cas/%s' % (self.server_path, csig)

    def _get_task_cache_url(self, task):
        """Retrieves the URL for the specified task's metadata."""
        return '%s/ac/%s' % (self.server_path,
                             self._get_task_metadata_signature(task))

    def _get_task_metadata_signature(self, task):
        """
        Retrieves the SHA-256 signature that represents the task in the remote
        cache. This is used to look up task metadata in the remote cache.

        Important note 1: if you ever change the output of _get_task_metadata,
        you must also change metadata_version.

        Important note 2: When SCons supports SHA1 for content signatures, the
        "alternative-hash-md5" string will need to be dynamic.
        """
        sig_info = [
            'scons-metadata-version-%d' % self.metadata_version,
            'os-platform=%s' % self.os_platform,
        ] + [t.get_cachedir_bsig() for t in task.targets]
        return SCons.Util.hash_signature(';'.join(sig_info))

    def _get_task_metadata(self, task):
        """
        Retrieves the JSON metadata that we want to push to the action cache,
        dumped to a string and encoded using UTF-8.

        As we are using the Bazel remote cache server, which validates the
        entries placed into /ac/, this must match the JSON encoding of Bazel's
        ActionResult protobuf message from remote_execution.proto.
        """
        output_files = []
        is_posix = os.name == 'posix'
        for t in task.targets:
            output_file = {
                'path': t.path,
                'digest': {
                    'hash': t.get_csig(),
                    'sizeBytes': t.get_size(),
                },
            }
            if is_posix:
                output_file['isExecutable'] = t.fs.access(t.abspath, os.X_OK)
            output_files += [output_file]
        return json.dumps({'outputFiles': output_files}).encode('utf-8')

    def set_fetch_response_queue(self, queue):
        """
        Sets the queue used to report cache fetch results if fetching
        is enabled.
        """
        self.fetch_response_queue = queue

    def fetch_task(self, task):
        """
        Dispatches a request to a helper thread to fetch a task from the
        remote cache.

        Returns tuple with two booleans:
            [0]: True if we submitted the task to the thread pool and False
                 in all other cases.
            [1]: True if the task is cacheable *and* caching was enabled at
                 some point in the build. False otherwise.
        """
        if not (self.fetch_enabled and task.is_cacheable()):
            # Caching is not enabled in general or for this task.
            return False, False
        elif (not self.fetch_enabled_currently and
              not self._try_reset_failure()):
            # The cache is currently disabled.
            return False, True
        else:
            self.executor.submit(self._fetch, task)
            return True, True

    def push_task(self, task):
        """
        Dispatches a request to a helper thread to push a task to the
        remote cache.
        """
        if not self.push_enabled or not task.is_cacheable():
            return

        if self.push_enabled_currently or self._try_reset_failure():
            self.executor.submit(self._push, task)

    def _request_nodes(self, node_tuples):
        """
        Makes a GET request to the server for each of the specific Node content
        signatures.

        Returns True if all requests succeeded, False otherwise.
        """
        if not node_tuples:
            return True

        if len(node_tuples) == 1:
            # Optimize this common case by not going to the ThreadPoolExecutor.
            # That would just cause unnecessary delays due to thread scheduling
            # and waiting for locks.
            return self._request(node_tuples[0], None)
        else:
            # We need to make more than one request and doing it serially would
            # cause unnecessary delays for high-latency connections. urllib3 is
            # a synchronous API so we work around that by doing the requests
            # in a helper thread pool.
            responses_left = len(node_tuples)
            all_files_present = True
            result_queue = queue.Queue(0)

            for node_tuple in node_tuples:
                self.request_executor.submit(self._request, node_tuple,
                                             result_queue)

            while responses_left > 0:
                success = result_queue.get()
                all_files_present = \
                    all_files_present and success
                responses_left -= 1

            return all_files_present

    def _track_request(self, verb, url, target_path, *args, **kwargs):
        """
        Wraps a GET request, tracking response time and optionally logging
        details of the response.

        Supported parameters:
            verb (String): Verb to request (PUT or GET).
            url (String): URL to make the request to.
            target_path (String): None if it's a metadata request. Otherwise,
                                  the relative or absolute path for the target
                                  we are putting/getting.
            args/kwargs: Params to be passed into connection_pool.request.
        """
        start = datetime.datetime.now()
        is_metadata_request = target_path is None

        response = None
        try:
            if verb == 'GET':
                response = self.connection_pool.request(verb, url, *args,
                                                        **kwargs)
            else:
                response = self.connection_pool.urlopen(verb, url, *args,
                                                        **kwargs)
            exception = None
        except Exception as e:
            exception = e

        if self.debug_file:
            with self.stats_lock:
                ms = self._get_delta_ms(start)
                if is_metadata_request:
                    self.stats_metadata_requests += 1
                    self.stats_metadata_total_ms += ms
                elif response is not None and self._success(response):
                    # /cas/ requests only provide good tracking data if they
                    # succeeded. Otherwise, the actual uploaded/downloaded size
                    # is unknown and would skew our averages.
                    if verb == 'GET':
                        self.stats_download_requests += 1
                        self.stats_download_total_ms += ms
                        self.stats_download_total_bytes += len(response.data)
                    else:
                        self.stats_upload_requests += 1
                        self.stats_upload_total_ms += ms
                        self.stats_upload_total_bytes += len(kwargs['body'])

            ms = self._get_delta_ms(start)
            # target_path could be relative or absolute. Convert to relative.
            target_log = (('for target %s ' % self.fs.File(target_path).path)
                          if target_path else '')

            if exception:
                self._debug(
                    '%s FAILED exception %s: URL %s %s(%d ms elapsed).' %
                    (verb, exception, url, target_log, ms))
            else:
                if self._success(response):
                    self._debug('%s SUCCESS: URL %s %s(%d ms elapsed).' %
                                (verb, url, target_log, ms))
                else:
                    self._debug(
                        '%s FAILED %d (%s): URL %s %s(%d ms elapsed).' %
                        (verb, response.status, response.reason, url,
                         target_log, ms))

        if exception:
            raise exception

        return response

    def _validate_file(self, request_data, csig, size, path):
        """Validates that the downloaded file data is correct

        This function verifies that request_data matches the expected size in
        bytes and SHA-256 content signature.

        Returns True if it was successfully validated, False otherwise.
        """
        actual_size = len(request_data)
        if actual_size != size:
            # Validate the size of the downloaded data.
            self.log('Size mismatch downloading file "%s". Expected size %d, '
                     'got %d.' % (path, size, actual_size))
            return False

        # Validate the hash of the downloaded data. We only use SHA-256 in
        # so we only need to check for that.
        csig_length = len(csig)
        if csig_length == 64:
            actual_csig = SCons.Util.hash_signature(request_data)
        else:
            self.log('WARNING: Not validating csig %s (path "%s") because '
                     'hash length %d is of an unknown format.' %
                     (csig, path, csig_length))
            actual_csig = None

        if actual_csig is not None and actual_csig != csig:
            self.log('Hash mismatch downloading file "%s". Expected hash '
                     '%s, but got %s.' % (path, csig, actual_csig))
            return False

        return True

    def _request(self, node_tuple, result_queue):
        """
        Implementation of sending a GET request to the remote cache for a
        specific node.

        This function can be called multiple times from different threads
        in the ThreadPoolExecutor, so it must be thread-safe.

        Params:
            node_tuple (tuple): Tuple of node absolute path, csig, size, and
                                is_executable. is_executable is only used for
                                GET requests on Posix systems.
            result_queue (Queue): Optional queue to post Boolean result to.

        Returns True if the request succeeded, False otherwise.
        """
        (path, csig, size, is_executable) = node_tuple

        try:
            # XXX TODO: Stream responses to GET requests by passing
            # preload_content=False.
            response = self._track_request(
                'GET', self._get_node_data_url(csig), path,
                timeout=self.transfer_request_timeout_sec)

            if self._success(response):
                # Validate that the data has the correct signature and size.
                success = self._validate_file(response.data, csig, size, path)
                if success:
                    with open(path, 'wb') as f:
                        f.write(response.data)

                    if os.name == 'posix' and is_executable:
                        self.fs.chmod(
                            path, self.fs.stat(path).st_mode |
                            stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

                if result_queue:
                    result_queue.put(success)
                return success
        except urllib3.exceptions.HTTPError as e:
            # Host is not available. Immediately disable caching.
            self.log('GET request failed for file %s with exception: %s' %
                     (path, e))
            self._handle_failure()
        except Exception as e:
            import traceback
            self.log('Unexpected exception making GET request for file %s: '
                     '%s, %s' % (path, e, traceback.format_exc()))
            self._handle_failure()

        if result_queue:
            result_queue.put(False)
        return False

    def _success(self, response):
        """Wraps some logic to determine whether the request succeeded."""
        return response.status < 400 or response.status >= 600

    def _get_nodes_from_task_metadata(self, task_metadata):
        """Retrieves node tuples from the task metadata.

        Returns a list of tuples with the following entries:
            1. Absolute path to the file.
            2. File content signature.
            3. Size in bytes.
            4. True if the file should be marked as executable on Posix, False
               otherwise.
        """
        nodes = []
        for output_file in task_metadata['outputFiles']:
            path = output_file.get('path', None)
            if path:
                path = self.fs.File(path).abspath
            digest = output_file.get('digest', None)
            csig = digest.get('hash', None)
            size = int(digest.get('sizeBytes', '0'))
            is_executable = output_file.get('isExecutable', False)

            if path and digest and csig:
                nodes.append((path, csig, size, is_executable))
        return nodes

    def _get_delta_ms(self, start):
        """
        Helper function to return the difference in milliseconds between now
        and the specified start time.
        """
        delta = datetime.datetime.now() - start
        return delta.total_seconds() * 1000

    def _fetch(self, task):
        """
        Implementation of fetching a task from a remote cache.

        This function can be called multiple times from different threads
        in the ThreadPoolExecutor, so it must be thread-safe.
        """
        try:
            url = self._get_task_cache_url(task)

            # Fetch the task metadata from the server, if it exists.
            # Catch JSON decoding errors in case we received a partial
            # response from the server or the stored cache data is incomplete.
            response = self._track_request(
                'GET', url, None,
                headers={'Accept': 'application/json'},
                timeout=self.metadata_request_timeout_sec)
            action_result = None
            if self._success(response):
                try:
                    action_result = json.loads(response.data.decode('utf-8'))
                except json.JSONDecodeError as e:
                    if self.debug_file:
                        self._debug('Cache miss due to bad JSON data in the '
                                    'action cache for task with url %s, '
                                    'targets %s. Exception: %s' %
                                    (url, [str(t) for t in task.targets], e))
                except Exception as e:
                    self.log('Received unexpected exception %s when trying to '
                             'decode JSON data for task with url %s, targets '
                             '%s' % (e, url, [str(t) for t in task.targets]))

            if action_result:
                nodes = self._get_nodes_from_task_metadata(action_result)

                if not nodes:
                    # The task metadata couldn't be processed.
                    if self.debug_file:
                        self._debug('Cache miss for task with url %s, targets '
                                    '%s due to bad /ac/ record.' %
                                    (url, [str(t) for t in task.targets]))
                elif self._request_nodes(nodes):
                    # All downloads were successful. The main python thread
                    # marks nodes as built, so we must deliver csig and size
                    # info in a format expected by the
                    # Task.executed_with_callbacks function.
                    target_infos = [(csig, size) for _, csig, size, _ in nodes]

                    # Mark each target as cached so it isn't unnecessarily
                    # pushed back to cache.
                    for t in task.targets:
                        t.cached = 1

                    # Optionally print information about the cache hit.
                    if self.debug_file:
                        self._debug_cache_result(True, task, url)

                    # Optionally push the result to the response queue.
                    if self.fetch_response_queue:
                        self.fetch_response_queue.put((task, True,
                                                       target_infos))
                    return True
                elif self.debug_file:
                    self._debug('Cache miss for task with url %s, targets '
                                '%s due to missing /cas/ record.' %
                                (url, [str(t) for t in task.targets]))
            elif self.debug_file:
                self._debug_cache_result(False, task, url)
        except urllib3.exceptions.HTTPError as e:
            # Host could not be reached.
            self.log('GET request failed for task (targets=%s) with '
                     'exception: %s' % ([str(t) for t in task.targets], e))
            self._handle_failure()
        except Exception as e:
            import traceback
            self.log('Unexpected exception fetching task (targets=%s): '
                     '%s, %s' %
                     ([str(t) for t in task.targets], e,
                      traceback.format_exc()))
            self._handle_failure()

        # This is the failure path. Unlink any retrieved files and indicate
        # failure.
        for t in task.targets:
            if t.fs.exists(t.abspath):
                t.fs.unlink(t.abspath)

        # Push the result to the response queue.
        if self.fetch_response_queue:
            self.fetch_response_queue.put((task, False, None))
        else:
            self.log('Unexpectedly unable to find a response queue to '
                     'push the remote cache fetch result to.')

    def _push(self, task):
        """
        Implementation of pushing a task to a remote cache.

        This function can be called multiple times from different threads
        in the ThreadPoolExecutor, so it must be thread-safe.

        :param task: Task instance to push.
        """
        try:
            # Push each node first then push the task info.
            for t in task.targets:
                response = self._track_request(
                    'PUT', self._get_node_data_url(t.get_csig()), t.path,
                    body=t.get_contents(),
                    timeout=self.transfer_request_timeout_sec)

                if not self._success(response):
                    # If the write failed, don't continue, because we don't
                    # want to write the metadata.
                    return

            # All target writes succeeded, so write the metadata.
            response = self._track_request(
                'PUT', self._get_task_cache_url(task), None,
                body=self._get_task_metadata(task),
                headers={'Content-Type': 'application/json'},
                timeout=self.metadata_request_timeout_sec)

        except urllib3.exceptions.HTTPError as e:
            # Host is not available.
            self.log('PUT request failed for task (targets=%s) with '
                     'exception: %s' % ([str(t) for t in task.targets], e))
            self._handle_failure()
        except Exception as e:
            import traceback
            self.log('Unexpected exception pushing task (targets=%s): '
                     '%s, %s' %
                     ([str(t) for t in task.targets], e,
                      traceback.format_exc()))
            self._handle_failure()

    def close(self):
        """Releases any resources that this class acquired."""
        if self.executor is not None:
            # Async fetches shouldn't still be pending at this point, but
            # async pushes could.
            start = datetime.datetime.now()
            self.executor.shutdown(wait=True)
            if self.debug_file:
                # Log a debug message if shutting down the network request
                # executor took a while. This happens if there are large
                # cache pushes at the end of the build.
                ms = self._get_delta_ms(start)
                if ms > 100:
                    self._debug('Shutting down took %d ms.' % ms)

            self.executor = None

        for _, session in self.sessions.items():
            session.close()
        self.sessions.clear()

        if self.debug_file not in [None, sys.stdout]:
            self.debug_file.close()
            self.debug_file = None

    def _get_monotonic_now(self):
        """ """
        if sys.version_info[:2] >= (3, 3):
            return time.monotonic()
        else:
            return time.clock()

    def _handle_failure(self):
        """Disables remote caching if there were too many failures."""
        self.failure_count += 1
        self.total_failure_count += 1

        now = self._get_monotonic_now()
        cache_ok_since = self.cache_ok_since

        if (self.failure_count > self.request_failure_threshold and
                (self.push_enabled_currently or
                 self.fetch_enabled_currently)):

            cache_ok_duration = now - cache_ok_since

            # Note: backoff_remission_sec above is not scaled by the
            #       multiplier today. We may revisit that design choice later.
            if (self.reset_count and
                    (not self.backoff_remission_sec or
                     cache_ok_duration < self.backoff_remission_sec)):
                # This is an exponential backoff scenario.
                backoff_multiplier = (
                    self.current_reset_backoff_multiplier *
                    self.reset_backoff_multiplier)
            else:
                # Either this is the first failure or the enough time
                # passed to reset the exponential backoff.
                backoff_multiplier = 1.0

            reset_text = 'RemoteCache: Request failure threshold was reached.'

            if self.reset_delay_sec:
                # If the server is down, we don't want everybody trying to
                # hit it all at once, so add some randomness.
                # random.randint() requires that reset_skew_sec be an int.
                reset_skew_sec = int(self.reset_skew_sec * backoff_multiplier)
                reset_delay_sec = self.reset_delay_sec * backoff_multiplier

                skew = random.randint(-reset_skew_sec, reset_skew_sec)
                delay = reset_delay_sec + skew

                # Set cache_ok_since into the future.
                self.cache_ok_since = now + delay

                reset_text += (' Suspending remote caching, attempting '
                               'restart in %2.1f seconds.' % delay)
            else:
                reset_text += ' Disabling remote caching.'

            self.log(reset_text)
            self.current_reset_backoff_multiplier = backoff_multiplier
            self.push_enabled_currently = False
            self.fetch_enabled_currently = False
        elif cache_ok_since < now:
            # The cache has behaved unhealthy up until this point.
            # Note: cache_ok_since points into the future when the cache is
            #       disabled and we're waiting for a reset.
            self.cache_ok_since = now

    def _try_reset_failure(self):
        """
        Attempts to restart the cache fetch and push logic if the appropriate
        amount of time has passed. Exponenial backoff is implemented as well.
        :return: False is the reset deadline hasn't passed yet.
        """
        if not self.reset_delay_sec:
            return False

        now = self._get_monotonic_now()

        # When the cache is suspended, cache_ok_since is set into the future.
        # once we reach that point, we re-enable it.
        if now < self.cache_ok_since:
            return False

        self.log('RemoteCache: Resuming remote caching attempts.')
        self.reset_count += 1
        self.failure_count = 0
        self.fetch_enabled_currently = self.fetch_enabled
        self.push_enabled_currently = self.push_enabled
        return True

    def _debug(self, msg):
        """
        Prints a debug message if --cache-debug was set.
        Caller is responsible for checking that self.debug_file is not None.
        """
        if self.debug_file:
            self.debug_file.write(msg + '\n')

    def _debug_cache_result(self, hit, task, url):
        """
        Prints the result of a task lookup to debug_file.
        Caller is responsible for checking that self.debug_file is not None.
        """
        t = task.targets[0]
        executor = t.get_executor()
        try:
            # Print the raw executor contents without any subst calls. This
            # makes it easier to compare hit and miss records across builds.
            # Avoid using executor.get_contents() because it uses ''.join()
            # and doesn't print well.
            actions = [action.get_contents(executor.get_all_targets(),
                                           executor.get_all_sources(),
                                           executor.get_build_env()).decode()
                       for action in executor.get_action_list()]
        except Exception:
            # Actions that run Python functions fail because they can't
            # be printed raw. Instead, convert directly to string.
            actions = [str(executor)]

        def format_container(container):
            """
            Returns the contents of the container, preserving space by putting
            consecutive entries from the same directory on the same line. It is
            extremely important that order is maintained in the outputted list,
            so this function cannot do any sorting. This also means that the
            same directory may show up multiple times in the returned string
            if all files from that directory are not adjacent in the
            container.
            """
            lastdir = None
            result = ''
            for c in container:
                dir = getattr(c, 'dir', None)
                name = getattr(c, 'name', '')
                # Note: this code uses concatenation instead of % formatting
                # for better performance.
                if dir is None:
                    result += '\n\t' + str(c)
                elif dir != lastdir:
                    result += '\n\t' + str(dir) + ': ' + str(name)
                else:
                    result += ', ' + str(name)
                lastdir = dir
            return result if result else ' None'

        # To be cacheable, there needs to be at least one file target, which
        # means that we expect sources, depends, and implicit to be set.
        # However, ignore may not be set.
        self._debug('Cache %s for task with url %s.\nTargets:%s\n'
                    'Sources:%s\nDepends:%s\nImplicit:%s\nIgnore:%s\n'
                    'Actions:\n\t%s' %
                    ('hit' if hit else 'miss', url,
                     format_container(task.targets),
                     format_container(t.sources),
                     format_container(t.depends),
                     format_container(t.implicit),
                     format_container(getattr(t, 'ignore', [])),
                     '\n\t'.join(actions)))

    def _print_operation_stats(self, operation, requests, bytes, ms):
        """Prints statistics about the specified operation."""
        if requests > 0:
            mb = float(bytes) / 1048576
            seconds = float(ms) / 1000
            self._debug('%s stats: %d requests on %d MB took %d ms. Average '
                        '%2.2f ms per MB and %2.2f MB per second.' %
                        (operation, requests, mb, ms,
                         0 if mb == 0 else float(ms) / mb,
                         0 if seconds == 0 else mb / seconds))

    def log_stats(self, hit_pct, cache_count, cache_hits, cache_misses,
                  cache_suspended, cacheable_pct, cache_skips, task_count,
                  total_failures, reset_count):
        """
        Prints the statistics that were collected during a build.
        """
        message = (
            '%2.1f percent cache hit rate on %d cacheable tasks with %d hits, '
            '%d misses, %d w/cache suspended. %2.1f percent of total tasks '
            'cacheable, due to %d/%d tasks marked not cacheable. Saw %d total '
            'failures, %d cache restarts.' %
            (hit_pct, cache_count, cache_hits, cache_misses,
             cache_suspended,
             cacheable_pct, cache_skips, task_count,
             total_failures, reset_count)
        )
        self.log('RemoteCache: %s' % message)

        if self.debug_file:
            self._debug(message)

            if self.stats_metadata_requests > 0:
                self._debug('Task metadata stats: %d ms average RTT on %d '
                            'requests.' %
                            (self.stats_metadata_total_ms /
                             self.stats_metadata_requests,
                             self.stats_metadata_requests))

            # The upload and download stats use the same log format.
            self._print_operation_stats('Download',
                                        self.stats_download_requests,
                                        self.stats_download_total_bytes,
                                        self.stats_download_total_ms)
            self._print_operation_stats('Upload',
                                        self.stats_upload_requests,
                                        self.stats_upload_total_bytes,
                                        self.stats_upload_total_ms)

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
