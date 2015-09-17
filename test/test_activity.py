#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

from __future__ import unicode_literals

import time
import json

import pytest
import tabun_api as api
from tabun_api.compat import text

from testutil import load_file, set_mock, user


def test_get_activity_tabun(user):
    items_data = json.loads(load_file('activity_items.json', template=False).decode('utf-8'))

    last_id, items = user.get_activity()
    assert last_id == 15000

    # assert len(items) == len(items_data)
    for data, item in zip(items_data, items):
        print(item)
        for key, value in data.items():
            if key == "date":
                assert time.strftime("%Y-%m-%d %H:%M", item.date) == value
            else:
                assert getattr(item, key) == value


def test_get_activity_livestreet(user, set_mock):
    set_mock({'/stream/all/': 'activity_ls.html'})
    items_data = json.loads(load_file('activity_items.json', template=False).decode('utf-8'))

    last_id, items = user.get_activity()
    assert last_id == 15000

    # assert len(items) == len(items_data)
    for data, item in zip(items_data, items):
        print(item)
        for key, value in data.items():
            if key == "date":
                assert time.strftime("%Y-%m-%d %H:%M", item.date) == value
            else:
                assert getattr(item, key) == value


def test_get_more_activity(user, set_mock):
    answer = '{"iStreamLastId":"15000","result":%DATA%,"events_count":11,"sMsgTitle":"","sMsg":"","bStateError":false}'
    answer = answer.replace('%DATA%', json.dumps(load_file('activity_items.html', template=False).decode('utf-8')))

    set_mock(
        {
            '/stream/get_more_all/': (None, {
                'data': answer.encode('utf-8'),
                'headers': {'Content-Type': 'application/json'},
            })
        }
    )

    items_data = json.loads(load_file('activity_items.json', template=False).decode('utf-8'))

    last_id, items = user.get_more_activity()
    assert last_id == 15000

    # assert len(items) == len(items_data)
    for data, item in zip(items_data, items):
        print(item)
        for key, value in data.items():
            if key == "date":
                assert time.strftime("%Y-%m-%d %H:%M", item.date) == value
            else:
                assert getattr(item, key) == value
