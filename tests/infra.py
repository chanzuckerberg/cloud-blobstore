import collections.abc
import functools
import inspect
import json
import logging
import os
import pprint
import re
import time
import typing
import uuid

import boto3
import requests
from flask import wrappers
from typing import Any

from dss.util import UrlBuilder


def start_verbose_logging():
    logging.basicConfig(level=logging.INFO)
    for logger_name in logging.Logger.manager.loggerDict:  # type: ignore
        if logger_name.startswith("botocore") or logger_name.startswith("boto3.resources"):
            logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_env(varname):
    if varname not in os.environ:
        raise RuntimeError(
            "Please set the {} environment variable".format(varname))
    return os.environ[varname]


class ExpectedErrorFields(typing.NamedTuple):
    code: str

    status: typing.Optional[int] = None
    """
    If this is None, then we not check the status.  For all other values, we test that it matches.
    """

    expect_stacktrace: typing.Optional[bool] = None
    """
    If this is True, then we expect the stacktrace to be present.  If this is False, then we expect the stacktrace to be
    absent.  If this is None, then we do not test the presence of the stacktrace.
    """


class DSSAssertResponse(typing.NamedTuple):
    response: wrappers.Response
    body: str
    json: typing.Optional[typing.Any]


class DSSAsserts:
    sre = re.compile("^assert(.+)Response")

    def assertResponse(
            self,
            method: str,
            path: str,
            expected_code: typing.Union[int, typing.Container[int]],
            json_request_body: typing.Optional[dict]=None,
            expected_error: typing.Optional[ExpectedErrorFields]=None,
            **kwargs) -> DSSAssertResponse:
        """
        Make a request given a HTTP method and a path.  The HTTP status code is checked against `expected_code`.

        If json_request_body is provided, it is serialized and set as the request body, and the content-type of the
        request is set to application/json.

        The first element of the return value is the response object.  The second element of the return value is the
        response text.  Attempt to parse the response body as JSON and return that as the third element of the return
        value.  Otherwise, the third element of the return value is None.

        If expected_error is provided, the content-type is expected to be "application/problem+json" and the response is
        tested in accordance to the documentation of `ExpectedErrorFields`.
        """
        if json_request_body is not None:
            if 'data' in kwargs:
                self.fail("both json_input and data are defined")
            kwargs['data'] = json.dumps(json_request_body)
            kwargs['content_type'] = 'application/json'

        response = getattr(self.app, method)(path, **kwargs)
        try:
            actual_json = json.loads(response.data.decode("utf-8"))
        except Exception:
            actual_json = None

        try:
            if isinstance(expected_code, collections.abc.Container):
                self.assertIn(response.status_code, expected_code)
            else:
                self.assertEqual(response.status_code, expected_code)

            if expected_error is not None:
                self.assertEqual(response.headers['content-type'], "application/problem+json")
                self.assertEqual(actual_json['code'], expected_error.code)
                self.assertIn('title', actual_json)
                if expected_error.status is not None:
                    self.assertEqual(actual_json['status'], expected_error.status)
                if expected_error.expect_stacktrace is not None:
                    self.assertEqual('stacktrace' in actual_json, expected_error.expect_stacktrace)
        except AssertionError:
            if actual_json is not None:
                print("Response:")
                pprint.pprint(actual_json)
            raise

        return DSSAssertResponse(response, response.data, actual_json)

    def assertHeaders(
            self,
            response: wrappers.Response,
            expected_headers: dict = {}) -> None:
        for header_name, header_value in expected_headers.items():
            self.assertEqual(response.headers[header_name], header_value)

    # this allows for assert*Response, where * = the request method.
    def __getattr__(self, item: str) -> typing.Any:
        if item.startswith("assert"):
            mo = self.sre.match(item)
            if mo is not None:
                method = mo.group(1).lower()
                return functools.partial(self.assertResponse, method)

        if hasattr(super(DSSAsserts, self), '__getattr__'):
            return super(DSSAsserts, self).__getattr__(item)  # type: ignore
        else:
            raise AttributeError(item)


class S3TestBundle:
    """
    A test bundle staged in S3

    This class does a little bit of "double duty" as we also use it to store the uuid and versions used with the API
    """
    BUCKET_TEST_FIXTURES = get_env('DSS_S3_BUCKET_TEST_FIXTURES')

    def __init__(self, path, bucket=BUCKET_TEST_FIXTURES):
        self.bucket = boto3.resource('s3').Bucket(bucket)
        self.path = path
        self.files = self.enumerate_bundle_files()
        self.uuid = str(uuid.uuid4())
        self.version = None

    def enumerate_bundle_files(self):
        object_summaries = self.bucket.objects.filter(Prefix=f"{self.path}/")
        return [S3File(objectSummary, self) for objectSummary in object_summaries]


class S3File:
    """
    A test file staged in S3
    """

    def __init__(self, object_summary, bundle):
        self.bundle = bundle
        self.path = object_summary.key
        self.metadata = object_summary.Object().metadata
        self.indexed = True if self.metadata['hca-dss-content-type'] == "application/json" else False
        self.name = os.path.basename(self.path)
        self.url = f"s3://{bundle.bucket.name}/{self.path}"
        self.uuid = str(uuid.uuid4())
        self.version = None


class DSSUploadMixin:
    def upload_file_wait(
            self: typing.Any,
            source_url: str,
            replica: str,
            file_uuid: str=None,
            bundle_uuid: str=None,
            timeout_seconds: int=120,
            expect_async: typing.Optional[bool]=None,
    ) -> DSSAssertResponse:
        """
        Upload a file.  If the request is being handled asynchronously, wait until the file has landed in the data
        store.
        """
        file_uuid = str(uuid.uuid4()) if file_uuid is None else file_uuid
        bundle_uuid = str(uuid.uuid4()) if bundle_uuid is None else bundle_uuid
        if expect_async is True:
            expected_codes = requests.codes.accepted
        elif expect_async is False:
            expected_codes = requests.codes.created
        else:
            expected_codes = requests.codes.created, requests.codes.accepted
        resp_obj = self.assertPutResponse(
            f"/v1/files/{file_uuid}",
            expected_codes,
            json_request_body=dict(
                bundle_uuid=bundle_uuid,
                creator_uid=0,
                source_url=source_url,
            ),
        )

        if resp_obj.response.status_code == requests.codes.accepted:
            # hit the GET /files endpoint until we succeed.
            start_time = time.time()
            timeout_time = start_time + timeout_seconds

            while time.time() < timeout_time:
                try:
                    self.assertHeadResponse(
                        f"/v1/files/{file_uuid}?replica={replica}",
                        requests.codes.ok)
                    break
                except AssertionError:
                    pass

                time.sleep(1)
            else:
                self.fail("Could not find the output file")

        return resp_obj


class StorageTestSupport:

    """
    Storage test operations for files and bundles.

    This class extends DSSAsserts, and like DSSAsserts,
    expects the client app to be available as 'self.app'
    """

    def upload_files_and_create_bundle(self, bundle: S3TestBundle):
        for s3file in bundle.files:
            version = self.upload_file(s3file)
            s3file.version = version
        self.create_bundle(bundle)

    def upload_file(self: typing.Any, bundle_file: S3File) -> str:
        response = self.upload_file_wait(
            bundle_file.url,
            "aws",
            file_uuid=bundle_file.uuid,
            bundle_uuid=bundle_file.bundle.uuid,
        )
        response_data = json.loads(response[1])
        self.assertIs(type(response_data), dict)
        self.assertIn('version', response_data)
        return response_data['version']

    def create_bundle(self: Any, bundle: S3TestBundle):
        response = self.assertPutResponse(
            str(UrlBuilder().set(path='/v1/bundles/' + bundle.uuid)
                .add_query('replica', 'aws')),
            requests.codes.created,
            json_request_body=self.put_bundle_payload(bundle)
        )
        response_data = json.loads(response[1])
        self.assertIs(type(response_data), dict)
        self.assertIn('version', response_data)
        bundle.version = response_data['version']

    @staticmethod
    def put_bundle_payload(bundle: S3TestBundle):
        payload = {
            'uuid': bundle.uuid,
            'creator_uid': 1234,
            'version': bundle.version,
            'files': [
                {
                    'indexed': bundle_file.indexed,
                    'name': bundle_file.name,
                    'uuid': bundle_file.uuid,
                    'version': bundle_file.version
                }
                for bundle_file in bundle.files
            ]
        }
        return payload

    def get_bundle_and_check_files(self: Any, bundle: S3TestBundle):
        response = self.assertGetResponse(
            str(UrlBuilder().set(path='/v1/bundles/' + bundle.uuid)
                .add_query('replica', 'aws')),
            requests.codes.ok
        )
        response_data = json.loads(response[1])
        self.check_bundle_contains_same_files(bundle, response_data['bundle']['files'])
        self.check_files_are_associated_with_bundle(bundle)

    def check_bundle_contains_same_files(self: Any, bundle: S3TestBundle, file_metadata: dict):
        self.assertEqual(len(bundle.files), len(file_metadata))
        for bundle_file in bundle.files:
            try:
                filedata = next(data for data in file_metadata if data['uuid'] == bundle_file.uuid)
            except StopIteration:
                self.fail(f"File {bundle_file.uuid} is missing from bundle")
            self.assertEqual(filedata['uuid'], bundle_file.uuid)
            self.assertEqual(filedata['name'], bundle_file.name)
            self.assertEqual(filedata['version'], bundle_file.version)

    def check_files_are_associated_with_bundle(self: Any, bundle: S3TestBundle):
        for bundle_file in bundle.files:
            response = self.assertGetResponse(
                str(UrlBuilder().set(path='/v1/files/' + bundle_file.uuid)
                    .add_query('replica', 'aws')),
                requests.codes.found,
            )
            self.assertEqual(bundle_file.bundle.uuid, response[0].headers['X-DSS-BUNDLE-UUID'])
            self.assertEqual(bundle_file.version, response[0].headers['X-DSS-VERSION'])


def generate_test_key() -> str:
    callerframerecord = inspect.stack()[1]  # 0 represents this line, 1 represents line at caller.
    frame = callerframerecord[0]
    info = inspect.getframeinfo(frame)
    filename = os.path.basename(info.filename)
    unique_key = str(uuid.uuid4())

    return f"{filename}/{info.function}/{unique_key}"
