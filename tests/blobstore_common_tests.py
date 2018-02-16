import io

import requests

from cloud_blobstore import BlobNotFoundError, BlobStore, BlobPagingError
from tests import infra


class BlobStoreTests:
    """
    Common blobstore tests.  We want to avoid repeating ourselves, so if we
    built the abstractions correctly, common operations can all be tested here.
    """

    def test_get_metadata(self):
        """
        Ensure that the ``get_metadata`` methods return sane data.
        """
        handle = self.handle  # type: BlobStore
        metadata = handle.get_user_metadata(
            self.test_fixtures_bucket,
            "test_good_source_data/0")
        self.assertIn('test_metadata', metadata)
        self.assertEqual(metadata['test_metadata'], "12345")

        with self.assertRaises(BlobNotFoundError):
            handle.get_user_metadata(
                self.test_fixtures_bucket,
                "test_good_source_data_DOES_NOT_EXIST")

    def test_get_content_type(self):
        """
        Ensure that the ``get_content_type`` methods return sane data.
        """
        handle = self.handle  # type: BlobStore
        content_type = handle.get_content_type(
            self.test_fixtures_bucket,
            "test_good_source_data/0")
        self.assertEqual(content_type, "text/plain")

        content_type = handle.get_content_type(
            self.test_fixtures_bucket,
            "test_good_source_data/1")
        self.assertEqual(content_type, "binary/octet-stream")

        with self.assertRaises(BlobNotFoundError):
            handle.get_content_type(
                self.test_fixtures_bucket,
                "test_good_source_data_DOES_NOT_EXIST")

    def testList(self):
        """
        Ensure that the ```list``` method returns sane data.
        """
        items = list(self.handle.list(
            self.test_fixtures_bucket,
            "test_good_source_data/0",
        ))
        self.assertIn("test_good_source_data/0", items)
        for item in items:
            if item == "test_good_source_data/0":
                break
        else:
            self.fail("did not find the requisite key")

        # fetch a bunch of items all at once.
        items = list(self.handle.list(
            self.test_fixtures_bucket,
            "testList/prefix",
        ))
        self.assertEqual(len(items), 10)

        # this should fetch both testList/delimiter and testList/delimiter/test
        items = list(self.handle.list(
            self.test_fixtures_bucket,
            "testList/delimiter",
        ))
        self.assertEqual(len(items), 2)

        # this should fetch only testList/delimiter
        items = list(self.handle.list(
            self.test_fixtures_bucket,
            "testList/delimiter",
            delimiter="/"
        ))
        self.assertEqual(len(items), 1)

    def testListV2(self):
        """
        Ensure that the ```list_v2``` method returns sane data.
        """
        items = list(self.handle.list_v2(
            self.test_fixtures_bucket,
            "test_good_source_data/0",
        ))
        self.assertIn("test_good_source_data/0", items)
        for item in items:
            if item == "test_good_source_data/0":
                break
        else:
            self.fail("did not find the requisite key")

        # fetch a bunch of items all at once.
        items = list(self.handle.list_v2(
            self.test_fixtures_bucket,
            "testList/prefix",
        ))
        self.assertEqual(len(items), 10)

        # fetch a bunch of items all at once with small page size
        items = list(self.handle.list_v2(
            self.test_fixtures_bucket,
            "testList/prefix",
            k_page_max=3
        ))
        self.assertEqual(len(items), 10)

        # this should fetch both testList/delimiter and testList/delimiter/test
        items = list(self.handle.list_v2(
            self.test_fixtures_bucket,
            "testList/delimiter",
        ))
        self.assertEqual(len(items), 2)

        # this should fetch only testList/delimiter
        items = list(self.handle.list_v2(
            self.test_fixtures_bucket,
            "testList/delimiter",
            delimiter="/"
        ))
        self.assertEqual(len(items), 1)

    def testListV2Continuation(self):
        self._testListV2Continuation(2, 3)
        self._testListV2Continuation(2, 4)

    def _testListV2Continuation(self, page_size, break_size):
        blobiter = self.handle.list_v2(
            self.test_fixtures_bucket,
            "testList/prefix",
            k_page_max=page_size,
        )

        items1 = list()
        items2 = list()

        for i, item in enumerate(blobiter):
            items1.append(
                item
            )
            if i >= break_size - 1:
                break

        blobiter = self.handle.list_v2(
            self.test_fixtures_bucket,
            "testList/prefix",
            token=blobiter.token,
            start_after_key=items1[-1],
            k_page_max=page_size,
        )

        items2 = [item for item in blobiter]

        self.assertEqual(len(items1) + len(items2), 10)

        # starting from an unfound start_after_key should raise an error
        with self.assertRaises(BlobPagingError):
            [item for item in
                self.handle.list_v2(
                    self.test_fixtures_bucket,
                    start_after_key="nonsensicalnonsene"
                )]

    def testGetPresignedUrl(self):
        presigned_url = self.handle.generate_presigned_GET_url(
            self.test_fixtures_bucket,
            "test_good_source_data/0",
        )

        resp = requests.get(presigned_url)
        self.assertEqual(resp.status_code, requests.codes.ok)

    def testUploadFileHandle(self):
        with self.subTest("without optional parameters"):
            fobj = io.BytesIO(b"abcabcabc")
            dst_blob_name = infra.generate_test_key()

            self.handle.upload_file_handle(
                self.test_bucket,
                dst_blob_name,
                fobj
            )

            # should be able to get metadata for the file.
            self.assertFalse(self.handle.get_user_metadata(self.test_bucket, dst_blob_name))

        with self.subTest("with optional parameters"):
            fobj = io.BytesIO(b"abcabcabc")
            dst_blob_name = infra.generate_test_key()

            content_type = "test/content-type"
            metadata = {"stuff": "things"}
            self.handle.upload_file_handle(
                self.test_bucket,
                dst_blob_name,
                fobj,
                content_type=content_type,
                metadata=metadata,
            )

            # should be able to get metadata for the file.
            self.assertEqual(self.handle.get_user_metadata(self.test_bucket, dst_blob_name), metadata)
            self.assertEqual(self.handle.get_content_type(self.test_bucket, dst_blob_name), content_type)

    def testGet(self):
        data = self.handle.get(
            self.test_fixtures_bucket,
            "test_good_source_data/0",
        )
        self.assertEqual(len(data), 11358)

        with self.assertRaises(BlobNotFoundError):
            self.handle.get(
                self.test_fixtures_bucket,
                "test_good_source_data_DOES_NOT_EXIST",
            )

    def testGetSize(self):
        sz = self.handle.get_size(self.test_fixtures_bucket, "test_good_source_data/0")
        self.assertEqual(sz, 11358)

    def testCopy(self):
        dst_blob_name = infra.generate_test_key()

        self.handle.copy(
            self.test_fixtures_bucket,
            "test_good_source_data/0",
            self.test_bucket,
            dst_blob_name,
        )

        # should be able to get metadata for the file.
        self.handle.get_user_metadata(
            self.test_bucket, dst_blob_name)

    def testDelete(self):
        fobj = io.BytesIO(b"abcabcabc")
        dst_blob_name = infra.generate_test_key()

        self.handle.upload_file_handle(
            self.test_bucket,
            dst_blob_name,
            fobj
        )

        # should be able to get metadata for the file.
        self.handle.get_user_metadata(
            self.test_bucket, dst_blob_name)

        self.handle.delete(self.test_bucket, dst_blob_name)

        with self.assertRaises(BlobNotFoundError):
            self.handle.get_user_metadata(
                self.test_bucket, dst_blob_name)

    def test_check_bucket_exists(self):
        """
        Ensure that the ``check_bucket_exists`` method returns true for FIXTURE AND TEST buckets.
        """
        handle = self.handle  # type: BlobStore
        self.assertEqual(handle.check_bucket_exists(self.test_fixtures_bucket), True)
        self.assertEqual(handle.check_bucket_exists(self.test_bucket), True)
        self.assertEqual(handle.check_bucket_exists('e47114c9-bb96-480f-b6f5-c3e07aae399f'), False)
