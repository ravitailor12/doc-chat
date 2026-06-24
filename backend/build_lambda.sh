#!/usr/bin/env bash
#
# Build a deployment zip for the PDF ingestion Lambda.
#
# Dependencies are downloaded as Linux wheels for the Lambda runtime, NOT for
# your local machine -- psycopg2-binary in particular must be the Linux build
# or the function fails at import time on AWS.
#
# Usage:
#   ./build_lambda.sh
#
# Then upload backend/lambda_deploy.zip to the Lambda console (or via CLI, see
# the bottom of this file). Set the Lambda runtime to python3.12 and the
# architecture to x86_64 to match what we build here.

set -euo pipefail

# --- target runtime (must match the Lambda config) ---
PY_VERSION="3.12"
PLATFORM="manylinux2014_x86_64"   # x86_64 Lambda. For arm64 use manylinux2014_aarch64.

cd "$(dirname "$0")"   # run from backend/

BUILD_DIR="build_lambda"
ZIP_FILE="lambda_deploy.zip"

echo ">> Cleaning previous build"
rm -rf "$BUILD_DIR" "$ZIP_FILE"
mkdir -p "$BUILD_DIR"

echo ">> Downloading dependencies as $PLATFORM wheels for Python $PY_VERSION"
python3 -m pip install \
    --requirement lambda_requirements.txt \
    --target "$BUILD_DIR" \
    --platform "$PLATFORM" \
    --python-version "$PY_VERSION" \
    --implementation cp \
    --only-binary=:all: \
    --upgrade

echo ">> Adding handler"
cp lambda_function.py "$BUILD_DIR/"

echo ">> Zipping"
# Zip from inside the build dir so files sit at the archive root (Lambda needs
# lambda_function.py at the top level, not nested under a folder).
( cd "$BUILD_DIR" && zip -qr "../$ZIP_FILE" . -x '*.pyc' -x '*__pycache__*' )

echo ">> Done: $(pwd)/$ZIP_FILE ($(du -h "$ZIP_FILE" | cut -f1))"
echo
echo "Upload it with:"
echo "  aws lambda update-function-code \\"
echo "    --function-name YOUR_FUNCTION_NAME \\"
echo "    --zip-file fileb://$(pwd)/$ZIP_FILE \\"
echo "    --region eu-north-1"
