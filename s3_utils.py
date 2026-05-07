"""
Utilidades compartidas para acceso a S3.
"""
import io
import os
from datetime import date

import boto3
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
    )


def get_bucket() -> str:
    bucket = os.getenv('S3_BUCKET')
    if not bucket:
        raise SystemExit("Falta S3_BUCKET en .env")
    return bucket


def download_bytes(key: str) -> bytes:
    bucket = get_bucket()
    s3 = get_s3_client()
    return s3.get_object(Bucket=bucket, Key=key)['Body'].read()


def list_data_files(prefix: str) -> list[str]:
    bucket = get_bucket()
    s3 = get_s3_client()
    keys = []
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.endswith('/'):
                continue
            if not key.lower().endswith(('.csv', '.xlsx', '.xls')):
                continue
            keys.append(key)
    return keys


def upload_dataframe_as_excel(df: pd.DataFrame, key: str) -> str:
    bucket = get_bucket()
    s3 = get_s3_client()
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')
    buffer.seek(0)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    return key


def build_dated_key(prefix: str, base_name: str, extension: str = 'xlsx') -> str:
    today = date.today().isoformat()
    return f"{prefix.rstrip('/')}/{base_name}_{today}.{extension}"
