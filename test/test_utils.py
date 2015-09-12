#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

from __future__ import unicode_literals

import pytest
from tabun_api import utils

from testutil import user


def test_htmlToString_with_cutted(user):
    post = user.get_post(138982, 'borderline')
    assert utils.htmlToString(post.body) == 'Текст до ката\n \nТекст после ката'


def test_htmlToString_without_cutted(user):
    post = user.get_post(138982, 'borderline')
    assert utils.htmlToString(post.body, with_cutted=False) == 'Текст до ката'


def test_htmlToString_with_cutted_spoiler(user):
    post = user.get_post(138983)
    assert utils.htmlToString(post.body) == 'Перед катом  После ката'


def test_htmlToString_with_cutted_with_spoiler_title(user):
    post = user.get_post(138983)
    assert utils.htmlToString(post.body, fancy=False) == 'Кат внутри спойлераПеред катом  После ката'


def test_htmlToString_without_cutted_spoiler(user):
    post = user.get_post(138983)
    assert utils.htmlToString(post.body, with_cutted=False) == 'Перед катом'


def test_find_images_cutted(user):
    post = user.get_post(138982, 'borderline')
    assert utils.find_images(post.body) == [['https://i.imgur.com/V3KzzyAs.png'], ['https://i.imgur.com/NAg929K.jpg']]


def test_parse_datetime_2015():
    assert utils.parse_datetime('2015-01-01T02:00:00+03:00').strftime('%Y-%m-%d %H:%M:%S') == '2014-12-31 23:00:00'


def test_parse_datetime_2015_noutc():
    assert utils.parse_datetime('2015-01-01T02:00:00+03:00', utc=False).strftime('%Y-%m-%d %H:%M:%S') == '2015-01-01 02:00:00'


def test_parse_datetime_2015_utc():
    assert utils.parse_datetime('2015-01-01T02:00:00Z').strftime('%Y-%m-%d %H:%M:%S') == '2015-01-01 02:00:00'


def test_parse_datetime_2014_04():
    assert utils.parse_datetime('2014-10-26T01:59:59+04:00').strftime('%Y-%m-%d %H:%M:%S') == '2014-10-25 21:59:59'


def test_parse_datetime_2014_03():
    assert utils.parse_datetime('2014-10-26T01:00:00+03:00').strftime('%Y-%m-%d %H:%M:%S') == '2014-10-25 22:00:00'
