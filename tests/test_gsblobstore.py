#!/usr/bin/env python
# coding: utf-8

import io
import os
import sys
import json
import unittest

import google.auth.transport.requests
import google.cloud.storage
from google.cloud.storage import Client
from google.oauth2 import service_account

pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # noqa
sys.path.insert(0, pkg_root)  # noqa

from cloud_blobstore import BlobNotFoundError, BlobStoreTimeoutError
from cloud_blobstore.gs import GSBlobStore
from tests import infra
from tests.blobstore_common_tests import BlobStoreTests


class TestGSBlobStore(unittest.TestCase, BlobStoreTests):
    def setUp(self):
        self.credentials = infra.get_env("GOOGLE_APPLICATION_CREDENTIALS")
        self.test_bucket = infra.get_env("GS_BUCKET")
        self.test_fixtures_bucket = infra.get_env("GS_BUCKET_FIXTURES")
        self.handle = GSBlobStore.from_auth_credentials(self.credentials)

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
        self.assertEqual(checksum, "e16e07b9")

        with self.assertRaises(BlobNotFoundError):
            handle.get_user_metadata(
                self.test_fixtures_bucket,
                "test_good_source_data_DOES_NOT_EXIST")

    def test_read_timeout(self):
        handle = self._get_handle_with_timeouts(read_timeout=0.00001)

        with self.assertRaises(BlobStoreTimeoutError):
            handle.upload_file_handle(
                self.test_bucket,
                "fake_key",
                io.BytesIO(os.urandom(1000))
            )

    def test_connect_timeout(self):
        google.cloud.storage.blob._RESUMABLE_URL_TEMPLATE = "https://www.chanzuckerberg.com:3000"
        handle = self._get_handle_with_timeouts(connect_timeout=0.1)

        with self.assertRaises(BlobStoreTimeoutError):
            handle.upload_file_handle(
                self.test_bucket,
                "fake_key",
                io.BytesIO(os.urandom(1000))
            )

    def _get_handle_with_timeouts(self, connect_timeout=60, read_timeout=60):
        class Session(google.auth.transport.requests.AuthorizedSession):
            def request(self, *args, **kwargs):
                kwargs['timeout'] = (connect_timeout, read_timeout)
                return super().request(*args, **kwargs)

        credentials = service_account.Credentials.from_service_account_file(
            self.credentials,
            scopes=Client.SCOPE
        )

        return GSBlobStore(Client(_http=Session(credentials)))

if __name__ == '__main__':
    unittest.main()
