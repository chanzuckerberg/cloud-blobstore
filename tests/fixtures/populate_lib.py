#!/usr/bin/env python

import os
import typing

from .cloud_uploader import GSUploader, S3Uploader, Uploader


def upload(uploader: Uploader):
    uploader.reset()

    # upload the "good" source files
    uploader.upload_file(
        "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
        "test_good_source_data/0",
        "text/plain",
        {
            "test_metadata": "12345",
        }
    )
    uploader.upload_file(
        "9cdc9050cecf59381fed55a2433140b69596fc861bee55abeafd1f9150f3e2da",
        "test_good_source_data/1",
    )

    # upload the files used for testList
    for ix in range(10):
        uploader.upload_file(
            "empty",
            "testList/prefix.{:03d}".format(ix)
        )
    uploader.upload_file(
        "empty",
        "testList/delimiter"
    )
    uploader.upload_file(
        "empty",
        "testList/delimiter/test"
    )


def populate(s3_bucket: typing.Optional[str], gs_bucket: typing.Optional[str]):
    # find the 'datafiles' subdirectory.
    root_dir = os.path.dirname(__file__)
    datafiles_dir = os.path.join(root_dir, "datafiles")

    uploaders = []  # type: typing.List[Uploader]
    if s3_bucket is not None:
        uploaders.append(S3Uploader(datafiles_dir, s3_bucket))
    if gs_bucket is not None:
        uploaders.append(GSUploader(datafiles_dir, gs_bucket))

    for uploader in uploaders:
        upload(uploader)
