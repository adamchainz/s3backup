# -*- coding: utf-8 -*-
import datetime
import json
import os

from botocore.exceptions import ClientError

from s3backup.sync import FileEntry


def to_timestamp(dt):
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    return (dt - epoch) / datetime.timedelta(seconds=1)


class S3SyncClient(object):

    def __init__(self, client, bucket, prefix):
        self.client = client
        self.bucket = bucket
        self.prefix = prefix

    def index_path(self):
        return os.path.join(self.prefix, '.index')

    def get_absolute_path(self, path):
        return os.path.join(self.prefix, path)

    def get_index_state(self):
        try:
            resp = self.client.get_object(
                Bucket=self.bucket,
                Key=self.index_path(),
            )
        except ClientError:
            return {}
        else:
            data = json.loads(resp['Body'].read().decode('utf-8'))
            results = {}
            for path, metadata in data.items():
                results[path] = FileEntry(path, timestamp=metadata['timestamp'])

            return results

    def get_current_state(self):
        results = {}
        resp = self.client.list_objects_v2(
            Bucket=self.bucket,
            Prefix=self.prefix,
        )
        if 'Contents' not in resp:
            return results

        for obj in resp['Contents']:
            key = os.path.relpath(obj['Key'], self.prefix)
            if key == '.index':
                continue

            results[key] = FileEntry(
                path=key,
                timestamp=to_timestamp(obj['LastModified']),
            )
        return results

    def update_index(self):
        data = {}
        for key, entry in self.get_current_state().items():
            data[key] = {'timestamp': entry.timestamp}

        self.client.put_object(
            Bucket=self.bucket,
            Key=self.index_path(),
            Body=json.dumps(data),
        )