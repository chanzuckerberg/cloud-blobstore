#!/usr/bin/env python
# coding: utf-8

import io
import os
import sys
import time
import unittest
import uuid
import select
import boto3
import botocore
import contextlib
import socket
from multiprocessing import Process, Manager
from http.server import BaseHTTPRequestHandler, HTTPServer
from botocore.vendored.requests.exceptions import ReadTimeout

pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # noqa
sys.path.insert(0, pkg_root)  # noqa

from cloud_blobstore import BlobNotFoundError, BlobStoreTimeoutError
from cloud_blobstore.s3 import S3BlobStore
from tests import infra
from tests.blobstore_common_tests import BlobStoreTests


class TestS3BlobStore(unittest.TestCase, BlobStoreTests):
    def setUp(self):
        self.test_bucket = infra.get_env("S3_BUCKET")
        self.test_fixtures_bucket = infra.get_env("S3_BUCKET_FIXTURES")
        self.test_us_east_1_bucket = infra.get_env("S3_BUCKET_US_EAST_1")
        self.test_non_us_east_1_bucket = infra.get_env("S3_BUCKET_NON_US_EAST_1")

        self.handle = S3BlobStore.from_environment()

    def tearDown(self):
        pass

    def test_get_checksum(self):
        """
        Ensure that the ``get_metadata`` methods return sane data.
        """
        handle = self.handle  # type: BlobStore
        checksum = handle.get_cloud_checksum(
            self.test_fixtures_bucket,
            "test_good_source_data/0")
        self.assertEqual(checksum, "3b83ef96387f14655fc854ddc3c6bd57")

        with self.assertRaises(BlobNotFoundError):
            handle.get_user_metadata(
                self.test_fixtures_bucket,
                "test_good_source_data_DOES_NOT_EXIST")

    def find_next_missing_parts_test_case(self, handle, parts_to_upload, *args, **kwargs):
        key = str(uuid.uuid4())
        mpu = handle.s3_client.create_multipart_upload(Bucket=self.test_bucket, Key=key)

        try:
            for part_to_upload in parts_to_upload:
                handle.s3_client.upload_part(
                    Bucket=self.test_bucket,
                    Key=key,
                    UploadId=mpu['UploadId'],
                    PartNumber=part_to_upload,
                    Body=f"part{part_to_upload:05}".encode("utf-8"))

            return handle.find_next_missing_parts(self.test_bucket, key, mpu['UploadId'], *args, **kwargs)
        finally:
            handle.s3_client.abort_multipart_upload(Bucket=self.test_bucket, Key=key, UploadId=mpu['UploadId'])

    def test_find_next_missing_parts_simple(self):
        handle = self.handle  # type: BlobStore

        # simple test case, 2 parts, 1 part uploaded.
        res = self.find_next_missing_parts_test_case(handle, [1], part_count=2)
        self.assertEqual(res, [2])

        res = self.find_next_missing_parts_test_case(handle, [1], part_count=2, search_start=1)
        self.assertEqual(res, [2])

        res = self.find_next_missing_parts_test_case(handle, [1], part_count=2, search_start=1, return_count=2)
        self.assertEqual(res, [2])

        res = self.find_next_missing_parts_test_case(handle, [1], part_count=2, search_start=2)
        self.assertEqual(res, [2])

        res = self.find_next_missing_parts_test_case(handle, [1], part_count=2, search_start=2, return_count=2)
        self.assertEqual(res, [2])

        with self.assertRaises(ValueError):
            self.find_next_missing_parts_test_case(handle, [1], part_count=2, search_start=3, return_count=2)

    def test_find_next_missing_parts_multiple_requests(self):
        handle = self.handle  # type: BlobStore

        # 10000 parts, one is uploaded.
        res = self.find_next_missing_parts_test_case(handle, [1], part_count=10000)
        self.assertEqual(res, [2])

        # 10000 parts, one is uploaded, get all the missing parts.
        res = self.find_next_missing_parts_test_case(handle, [1], part_count=10000, return_count=10000)
        self.assertEqual(len(res), 9999)
        self.assertNotIn(1, res)

        # 10000 parts, one is uploaded, get all the missing parts.
        res = self.find_next_missing_parts_test_case(handle, [1], part_count=10000, return_count=1000)
        self.assertEqual(len(res), 1000)
        self.assertNotIn(1, res)

        # 10000 parts, one is uploaded, get all the missing parts.
        res = self.find_next_missing_parts_test_case(handle, [1], part_count=10000, search_start=100, return_count=1000)
        self.assertEqual(len(res), 1000)
        self.assertNotIn(1, res)
        for missing_part in res:
            self.assertGreaterEqual(missing_part, 100)

        # 10000 parts, all the parts numbers divisible by 2000 is uploaded, get all the missing parts.
        res = self.find_next_missing_parts_test_case(
            handle,
            [ix
             for ix in range(1, 10000 + 1)
             if ix % 2000 == 0],
            part_count=10000,
            return_count=10000)
        self.assertEqual(len(res), 9995)
        for ix in range(1, 10000 + 1):
            if ix % 2000 == 0:
                self.assertNotIn(ix, res)
            else:
                self.assertIn(ix, res)

        # 10000 parts, all the parts numbers divisible by 2000 is uploaded, get all the missing parts starting at part
        # 1001.
        res = self.find_next_missing_parts_test_case(
            handle,
            [ix
             for ix in range(1, 10000 + 1)
             if ix % 2000 == 0],
            part_count=10000,
            search_start=1001,
            return_count=10000)
        self.assertEqual(len(res), 8995)
        for ix in range(1001, 10000 + 1):
            if ix % 2000 == 0:
                self.assertNotIn(ix, res)
            else:
                self.assertIn(ix, res)

    def test_get_bucket_region(self):
        """
        Ensure that the ``get_bucket_region`` method returns true for FIXTURE and TEST buckets.
        """
        handle = self.handle  # type: BlobStore
        self.assertEqual(handle.get_bucket_region(self.test_us_east_1_bucket), 'us-east-1')
        self.assertNotEqual(handle.get_bucket_region(self.test_non_us_east_1_bucket), 'us-east-1')

    def test_read_timeout(self):
        read_timeout = 1
        with contextlib.closing(ProxyConnectServer.start(2 * read_timeout)):
            config = botocore.config.Config(
                proxies={
                    'http': f'{ProxyConnectServer.address}:{ProxyConnectServer.shared_info["port"]}',
                    'https': f'{ProxyConnectServer.address}:{ProxyConnectServer.shared_info["port"]}',
                },
                read_timeout=read_timeout,
                retries={'max_attempts': 0}
            )
            s3_client = boto3.client('s3', config=config)
            handle = S3BlobStore(s3_client)

            # Make sure we actually raise a ReadError
            with self.assertRaises(ReadTimeout):
                s3_client.put_object(
                    Bucket=self.test_bucket,
                    Key='fake_key',
                    Body=os.urandom(1000)
                )

            # Make sure we correctly respond to a ReadError
            with self.assertRaises(BlobStoreTimeoutError):
                handle.upload_file_handle(
                    self.test_bucket,
                    'fake_key',
                    io.BytesIO(os.urandom(1000))
                )

    def test_connect_timeout(self):
        """
        Ensure that we handle botocore ConnectTimeouts
        """
        s3_client = boto3.client(
            's3',
            config=botocore.config.Config(
                retries={'max_attempts': 0}
            )
        )

        # Point boto to an unresponsive host
        s3_client._endpoint = botocore.endpoint.Endpoint(
            'https://www.chanzuckerberg.com:3000',
            '',
            s3_client._endpoint._event_emitter
        )
        handle = S3BlobStore(s3_client)

        with self.assertRaises(BlobStoreTimeoutError):
            handle.upload_file_handle(
                self.test_bucket,
                'fake_key',
                io.BytesIO(os.urandom(1000))
            )


def unused_tcp_port():
    with contextlib.closing(socket.socket()) as sock:
        sock.bind((ProxyConnectServer.address, 0))
        return sock.getsockname()[1]

class ProxyConnectServer(HTTPServer):
    address = '127.0.0.1'
    process = None
    manager = None
    shared_info = None

    def __init__(self, *args, shared_info=None, **kwargs):
        self.shared_info = shared_info
        super().__init__(*args, **kwargs)

    def server_activate(self, *args, **kwargs):
        super().server_activate(*args, **kwargs)
        ProxyConnectServer.shared_info['is_active'] = True

    @classmethod
    def start(cls, read_delay=0):
        cls.manager = Manager()

        shared_info = cls.manager.dict(
            read_delay=read_delay
        )
        cls.shared_info = shared_info

        class LazyRequestHandler(BaseHTTPRequestHandler):
            def do_CONNECT(self):
                address = self.path.split(':', 1)
                address[1] = int(address[1]) or 443
                s = socket.create_connection(address, timeout=self.timeout)
                self.send_response(200, 'Connection Established')
                self.end_headers()

                conns = [self.connection, s]
                self.close_connection = 0
                while not self.close_connection:
                    rlist, wlist, xlist = select.select(conns, [], conns, self.timeout)
                    if xlist or not rlist:
                        break
                    for r in rlist:
                        other = conns[1] if r is conns[0] else conns[0]
                        data = r.recv(8192)
                        if not data:
                            self.close_connection = 1
                            break
                        time.sleep(shared_info['read_delay'])
                        other.sendall(data)

        def eternity():
            port = unused_tcp_port()
            shared_info['port'] = port
            httpd = cls((cls.address, port), LazyRequestHandler, shared_info=shared_info)
            httpd.serve_forever()

        cls.process = Process(target=eternity)
        cls.process.start()

        while not shared_info.get('is_active', None):
            time.sleep(0.25)

        return cls

    @classmethod
    def close(cls):
        cls.process.terminate()
        cls.process = None
        cls.manager = None
        cls.shared_info = None

if __name__ == '__main__':
    unittest.main()
