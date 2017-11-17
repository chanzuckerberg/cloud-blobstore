#!/bin/bash

set -euo pipefail

if [[ $# != 2 ]]; then
    echo "Given an IAM principal intended to be used by a test/CI/CD pipeline,"
    echo "this script grants the principal the AWS IAM permissions necessary to"
    echo "test and deploy the DSS application. Run this script using privileged"
    echo "(IAM write access) IAM credentials."
    echo "Usage: $(basename $0) iam-principal-type iam-principal-name"
    echo "Example: $(basename $0) user hca-test"
    exit 1
fi

export iam_principal_type=$1 iam_principal_name=$2
export account_id=$(aws sts get-caller-identity | jq -r .Account)
policy_json="$(dirname $0)/../iam/policy-templates/ci-cd.json"
envsubst_vars='$S3_BUCKET $S3_BUCKET_FIXTURES $S3_BUCKET_US_EAST_1 $S3_BUCKET_NON_US_EAST_1 $account_id'

aws iam put-${iam_principal_type}-policy \
    --${iam_principal_type}-name $iam_principal_name \
    --policy-name hca-dss-ci-cd \
    --policy-document file://<(cat "$policy_json" | \
                                   envsubst "$envsubst_vars" | \
                                   jq -c 'del(.Statement[].Sid)')
