# cloud-blobstore

This library provides an abstraction layer for the most basic functionality provided by the cloud providers.  These are the basic functions required by the [Human Cell Atlas](https://www.humancellatlas.org/) [Data Storage Service](https://github.com/HumanCellAtlas/data-store).

## Development

### Set up your python environment
Before you start, you may wish to set up a [virtualenv](https://virtualenv.pypa.io/en/stable/).  Run `pip install -r requirements-dev.txt`. Then set up the following environment variables:

| Environment variable  | Explanation |
| --------------------- | ----------- |
| S3_BUCKET             | Points to the AWS S3 bucket where new files will be written.  It may be advisable to set up a cleanup policy for this bucket. |
| S3_BUCKET_FIXTURES    | Points to the AWS S3 bucket where static fixtures are stored. |
| GS_BUCKET             | Points to the GCP GS bucket where new files will be written.  It may be advisable to set up a cleanup policy for this bucket. |
| GS_BUCKET_FIXTURES    | Points to the GCP GS bucket where static fixtures are stored. |


### Set up test fixtures.
Run `python tests/fixtures/populate.py --s3-bucket $S3_BUCKET_FIXTURES --gs-bucket $GS_BUCKET_FIXTURES`

#### Running tests
Run `make test` in the top-level directory.
