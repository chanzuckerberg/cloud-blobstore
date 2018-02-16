#!/usr/bin/env python
# coding: utf-8

import os
import sys
import unittest

pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # noqa
sys.path.insert(0, pkg_root)  # noqa

from cloud_blobstore import BlobNotFoundError
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

    def test_check_bucket_exists(self):
        """
        Ensure that the ``check_bucket_exists`` method returns true for FIXTURE AND TEST buckets.
        """
        handle = self.handle  # type: BlobStore
        self.assertEqual(handle.check_bucket_exists(self.test_fixtures_bucket), True)
        self.assertEqual(handle.check_bucket_exists(self.test_bucket), True)
        self.assertEqual(handle.check_bucket_exists('e47114c9-bb96-480f-b6f5-c3e07aae399f'), False)


if __name__ == '__main__':
    unittest.main()
