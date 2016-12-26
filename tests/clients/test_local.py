# -*- coding: utf-8 -*-

import io
import json
import os
import shutil
import tempfile

import pytest

from s3backup.clients import local


def touch(path, mtime=None):
    if mtime is None:
        times = None
    else:
        times = (mtime, mtime)

    parent = os.path.dirname(path)
    if not os.path.exists(parent):
        os.makedirs(parent)

    with open(path, 'w'):
        os.utime(path, times)


class TestTraverse(object):
    def setup_method(self):
        self.target_folder = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.target_folder)

    def test_empty_folder(self):
        assert list(local.traverse(self.target_folder)) == []

    def test_correct_output(self):
        touch(os.path.join(self.target_folder, 'baz', 'zoo'))
        touch(os.path.join(self.target_folder, 'foo'))
        touch(os.path.join(self.target_folder, 'bar.md'))
        touch(os.path.join(self.target_folder, 'baz', 'bar'))
        touch(os.path.join(self.target_folder, '.index'))
        touch(os.path.join(self.target_folder, 'saw/.index'))

        actual_output = list(local.traverse(
            self.target_folder,
            ignore_files={'.index', '.idontexist'}
        ))

        expected_output = ['bar.md', 'baz/bar', 'baz/zoo', 'foo']
        assert actual_output == expected_output


class TestSyncObject(object):
    def test_repr(self):
        dev_null = open('/dev/null', 'r')
        sync_object = local.SyncObject(dev_null, 312313)
        assert repr(sync_object) == 'SyncObject<{}, 312313>'.format(dev_null)


class TestLocalSyncClient(object):
    def setup_method(self):
        self.target_folder = tempfile.mkdtemp()
        self.index_path = os.path.join(self.target_folder, '.index')

    def teardown_method(self):
        shutil.rmtree(self.target_folder)

    def test_repr(self):
        client = local.LocalSyncClient('/home/rick/timemachine/')
        assert repr(client) == 'LocalSyncClient</home/rick/timemachine/>'

    def set_index(self, data):
        with open(self.index_path, 'w') as fp:
            json.dump(data, fp)

    def get_file_data(self, key):
        with open(os.path.join(self.target_folder, key), 'rb') as fp:
            return fp.read()

    def set_file_data(self, key, data):
        with open(os.path.join(self.target_folder, key), 'wb') as fp:
            fp.write(data)

    def test_put_new(self):
        client = local.LocalSyncClient(self.target_folder)
        client.put(
            key='hello_world.txt',
            sync_object=local.SyncObject(io.BytesIO(b'hi'), 20000)
        )

        assert client.index['hello_world.txt']['remote_timestamp'] == 20000
        assert self.get_file_data('hello_world.txt') == b'hi'

    def test_put_existing(self):
        self.set_index({
            'doge.txt': {'local_timestamp': 1111111}
        })

        data = b'canis lupus familiaris'
        client = local.LocalSyncClient(self.target_folder)
        client.put(
            key='doge.txt',
            sync_object=local.SyncObject(io.BytesIO(data), 20000)
        )

        assert client.index['doge.txt']['remote_timestamp'] == 20000
        assert client.index['doge.txt']['local_timestamp'] == 1111111

        assert self.get_file_data('doge.txt') == data

    def test_get_existing(self):
        client = local.LocalSyncClient(self.target_folder)
        self.set_file_data('whatup.md', b'blue green yellow')
        sync_object = client.get('whatup.md')
        assert sync_object.fp.read() == b'blue green yellow'

    def test_get_non_existant(self):
        client = local.LocalSyncClient(self.target_folder)
        assert client.get('idontexist.md') is None

    def test_delete_existing(self):
        target_file = os.path.join(self.target_folder, 'foo')
        touch(os.path.join(self.target_folder, 'foo'), 222222)
        client = local.LocalSyncClient(self.target_folder)

        assert os.path.exists(target_file) is True
        client.delete('foo')
        assert os.path.exists(target_file) is False

    def test_delete_non_existant(self):
        client = local.LocalSyncClient(self.target_folder)
        with pytest.raises(IndexError) as exc:
            client.delete('idontexist.txt')
        assert exc.value.args[0] == 'The specified key does not exist: idontexist.txt'

    def test_index_path(self):
        client = local.LocalSyncClient(self.target_folder)
        assert client.index_path() == self.index_path

    def test_get_index_state(self):
        data = {
            'foo': {
                'local_timestamp': 4000,
                'remote_timestamp': 4000,
            },
            'bar/baz.txt': {
                'local_timestamp': 5000,
                'remote_timestamp': 5000,
            },
        }
        self.set_index(data)

        client = local.LocalSyncClient(self.target_folder)
        actual_output = client.get_index_state()
        assert actual_output == data

    def test_get_current_state(self):
        touch(os.path.join(self.target_folder, 'foo'), 13371337)
        touch(os.path.join(self.target_folder, 'bar'), 50032003)

        client = local.LocalSyncClient(self.target_folder)
        actual_output = client.get_current_state()
        expected_output = {
            'foo': {'local_timestamp': 13371337},
            'bar': {'local_timestamp': 50032003},
        }
        assert expected_output == actual_output

    def test_update_index_empty(self):
        touch(os.path.join(self.target_folder, 'foo'), 13371337)
        touch(os.path.join(self.target_folder, 'bar'), 50032003)

        client = local.LocalSyncClient(self.target_folder)
        client.update_index()
        actual_output = client.get_index_state()
        # remote timestamp should not be included since it does not exist
        expected_output = {
            'foo': {
                'local_timestamp': 13371337,
            },
            'bar': {
                'local_timestamp': 50032003,
            },
        }
        assert actual_output == expected_output
        assert client.index == expected_output

    def test_update_index_non_empty(self):
        touch(os.path.join(self.target_folder, 'foo'), 13371337)
        touch(os.path.join(self.target_folder, 'bar'), 50032003)

        self.set_index({
            'foo': {
                'local_timestamp': 4000,
                'remote_timestamp': 4000,
            },
            'bar': {
                'local_timestamp': 5000,
                'remote_timestamp': 5000,
            },
            'baz': {
                'local_timestamp': 5000,
                'remote_timestamp': 5000,
            }
        })

        client = local.LocalSyncClient(self.target_folder)
        client.update_index()
        actual_output = client.get_index_state()
        expected_output = {
            'foo': {
                'local_timestamp': 13371337,
                'remote_timestamp': 4000,
            },
            'bar': {
                'local_timestamp': 50032003,
                'remote_timestamp': 5000,
            },
        }
        assert actual_output == expected_output
        assert client.index == expected_output
