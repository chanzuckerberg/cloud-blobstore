import logging
import os
import typing

import boto3
from boto3.s3.transfer import TransferConfig
from google.cloud.storage import Client

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


AWS_MIN_CHUNK_SIZE = 64 * 1024 * 1024
"""Files must be larger than this before we consider multipart uploads."""
AWS_MAX_MULTIPART_COUNT = 10000
"""Maximum number of parts allowed in a multipart upload.  This is a limitation imposed by S3."""

def get_s3_chunk_size(filesize: int) -> int:
    if filesize <= AWS_MAX_MULTIPART_COUNT * AWS_MIN_CHUNK_SIZE:
        return AWS_MIN_CHUNK_SIZE
    else:
        div = filesize // AWS_MAX_MULTIPART_COUNT
        if div * AWS_MAX_MULTIPART_COUNT < filesize:
            div += 1
        return ((div + 1048575) // 1048576) * 1048576


class Uploader:
    def __init__(self, local_root: str) -> None:
        self.local_root = local_root

    def reset(self) -> None:
        raise NotImplementedError()

    def upload_file(
            self,
            local_path: str,
            remote_path: str,
            content_type: str="binary/octet-stream",
            metadata_keys: typing.Dict[str, str]=None,
            *args,
            **kwargs) -> None:
        raise NotImplementedError()


class S3Uploader(Uploader):
    def __init__(self, local_root: str, bucket: str) -> None:
        super(S3Uploader, self).__init__(local_root)
        self.bucket = bucket
        self.s3_client = boto3.client('s3')

    def reset(self) -> None:
        logger.info("%s", f"Emptying bucket: s3://{self.bucket}")
        s3 = boto3.resource('s3')
        s3.Bucket(self.bucket).objects.delete()

    def upload_file(
            self,
            local_path: str,
            remote_path: str,
            content_type: str="binary/octet-stream",
            metadata_keys: typing.Dict[str, str]=None,
            tags: typing.Dict[str, str]=None,
            *args,
            **kwargs) -> None:
        if metadata_keys is None:
            metadata_keys = dict()
        if tags is None:
            tags = dict()

        fp = os.path.join(self.local_root, local_path)
        sz = os.stat(fp).st_size

        chunk_sz = get_s3_chunk_size(sz)
        transfer_config = TransferConfig(
            multipart_threshold=64 * 1024 * 1024,
            multipart_chunksize=chunk_sz,
        )

        logger.info("%s", f"Uploading {local_path} to s3://{self.bucket}/{remote_path}")
        self.s3_client.upload_file(
            fp,
            self.bucket,
            remote_path,
            ExtraArgs={
                "Metadata": metadata_keys,
                "ContentType": content_type,
            },
            Config=transfer_config,
        )

        tagset = dict(TagSet=[])  # type: typing.Dict[str, typing.List[dict]]
        for tag_key, tag_value in tags.items():
            tagset['TagSet'].append(
                dict(
                    Key=tag_key,
                    Value=tag_value))
        self.s3_client.put_object_tagging(Bucket=self.bucket,
                                          Key=remote_path,
                                          Tagging=tagset)


class GSUploader(Uploader):
    def __init__(self, local_root: str, bucket_name: str) -> None:
        super(GSUploader, self).__init__(local_root)
        credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.gcp_client = Client.from_service_account_json(credentials)
        self.bucket = self.gcp_client.bucket(bucket_name)

    def reset(self) -> None:
        logger.info("%s", f"Emptying bucket: gs://{self.bucket.name}")
        for blob in self.bucket.list_blobs():
            blob.delete()

    def upload_file(
            self,
            local_path: str,
            remote_path: str,
            content_type: str="binary/octet-stream",
            metadata_keys: typing.Dict[str, str]=None,
            *args,
            **kwargs) -> None:
        logger.info("%s", f"Uploading {local_path} to gs://{self.bucket.name}/{remote_path}")
        blob = self.bucket.blob(remote_path)
        blob.upload_from_filename(os.path.join(self.local_root, local_path), content_type=content_type)
        if metadata_keys:
            blob.metadata = metadata_keys
            blob.patch()
