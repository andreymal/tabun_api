#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os
import cgi
import time
from io import BytesIO

import pytest

import tabun_api as api
from tabun_api.compat import urequest, text, text_types, binary, PY2

if PY2:
    from httplib import HTTPMessage
    def parse_headers(fp):
        return HTTPMessage(fp)
    import urlparse
else:
    from http.client import parse_headers
    from urllib import parse as urlparse

# для выбора загружаемых страниц из каталога data
guest_mode = False

data_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
file_cache = {}

templates = {
    'HEADER1': 'header1.html',
    'HEADER2': 'header2.html',
    'BODY': 'body.html',
    'AUTH1_GUEST': 'auth1_guest.html',
    'AUTH2_GUEST': 'auth2_guest.html',
    'AUTH1_AUTHORIZED': 'auth1_authorized.html',
    'AUTH2_AUTHORIZED': 'auth2_authorized.html',
    'NO_SIDEBAR': 'no_sidebar.html',
    'SIDEBAR': 'sidebar.html',
    'FOOTER': 'footer.html',
    'ACTIVITY_ITEMS': 'activity_items.html',
}

interceptors = {}
form_interceptors = {}
current_mocks = {}

mocks = {
    '/': ('index.html', None),
    '/blog/132085.html': ('132085.html', None),
    '/blog/borderline/138982.html': ('138982.html', None),
    '/blog/138983.html': ('138983.html', None),
    '/comments/': ('comments.html', None),
    '/stream/all/': ('activity.html', None),
}

@pytest.yield_fixture(scope='function')
def set_mock():
    try:
        yield load_mocks
    finally:
        clear_mock()


@pytest.yield_fixture(scope='function')
def intercept():
    def dfunc(url):
        def decorator(f):
            interceptors[url] = f
            return f
        return decorator
    try:
        yield dfunc
    finally:
        interceptors.clear()


@pytest.yield_fixture(scope='function')
def form_intercept():
    def dfunc(url):
        def decorator(f):
            form_interceptors[url] = f
            return f
        return decorator
    try:
        yield dfunc
    finally:
        form_interceptors.clear()


@pytest.yield_fixture(scope='function')
def as_guest():
    global guest_mode
    guest_mode = True
    try:
        yield
    finally:
        guest_mode = False


@pytest.fixture
def user():
    return UserTest()


def load_mocks(new_mocks):
    global current_mocks
    for key, value in new_mocks.items():
        current_mocks[key] = ((value, None) if isinstance(value, text_types) else value)


def clear_mock():
    current_mocks.clear()


def load_file(name, ignorekeys=(), template=True):
    # Загружаем файл или достаём из кэша
    path = os.path.join(data_dir, name)
    if name in file_cache:
        data = file_cache[name]
    else:
        data = open(path, 'rb').read()
        file_cache[name] = data

    if not template:
        return data

    # Для этих шаблонов имеется два режима — неавторизованного и авторизованного пользователя
    for metakey in ('AUTH1', 'AUTH2'):
        bmetakey = b'%' + metakey.encode('utf-8') + b'%'
        if metakey not in ignorekeys and bmetakey in data:
            key = (metakey + '_GUEST') if guest_mode else (metakey + '_AUTHORIZED')
            tname = templates[key]
            data = data.replace(metakey.encode('utf-8'), load_file(tname, ignorekeys + (key,)))

    # Пародируем шаблонизатор и включаем другие файлы в шаблон
    for key, tname in templates.items():
        bkey = b'%' + key.encode('utf-8') + b'%'
        if key not in ignorekeys and bkey in data:
            data = data.replace(bkey, load_file(tname, ignorekeys + (key,)))

    return data


def assert_data(obj, data, exclude=('post_id', 'comment_id')):
    for key, value in data.items():
        if key == 'time':
            assert time.strftime("%Y-%m-%d %H:%M:%S", obj.time) == value
        elif key == 'utctime':
            assert obj.utctime.strftime('%Y-%m-%d %H:%M:%S') == value
        elif key.startswith('context:'):
            assert obj.context[key[8:]] == value
        elif key not in exclude:
            assert getattr(obj, key) == value


def build_response(req_url, result_path, optparams=None):
    # Параметры ответа по умолчанию
    params = {
        'status': 200,
        'status_msg': 'OK',
        'headers': {
            'Content-Type': 'text/html; charset=utf-8',
            'Set-Cookie': [
                'TABUNSESSIONID=abcdef9876543210abcdef9876543210; path=/',
            ]},
        'url': req_url
    }
    # Параметры, переданные тестом
    if optparams:
        optparams = optparams.copy()
        params['headers'].update(optparams.pop('headers', {}))
        params.update(optparams)

    # Само содержимое подделываемого ответа на HTTP-запрос
    fp = BytesIO(load_file(result_path) if result_path else params.get('data', b''))

    # Собираем HTTP-заголовки
    raw_headers = ''
    for header, value in params['headers'].items():
        raw_headers += header + ': '
        if isinstance(value, (tuple, list)):
            raw_headers += ('\r\n' + header + ': ').join(value)
        else:
            raw_headers += value
        raw_headers += '\r\n'
    headers = parse_headers(BytesIO(raw_headers.encode('utf-8')))

    # Для некоторых ошибок нужно сгенерировать исключение
    if (params['status'] >= 500 or params['status'] in (404,)) and not params.get('noexc'):
        raise urequest.HTTPError(params['url'], params['status'], params['status_msg'], headers, fp)

    # Собираем ответ на HTTP-запрос
    resp = urequest.addinfourl(fp, headers, params['url'])
    resp.code = params['status']
    resp.msg = params['status_msg']
    return resp


class UserTest(api.User):
    def __init__(self, *args, **kwargs):
        super(UserTest, self).__init__(*args, **kwargs)

    def test_open(self, fullurl, data=None, timeout=None):
        if isinstance(fullurl, (text, binary)):
            req_url = fullurl
        else:
            assert data is None
            data = fullurl.data
            req_url = fullurl.get_full_url()

        # Тестируем совместимость с разными питонами и попутно собираем заголовки
        headers = {}
        if PY2:
            assert isinstance(req_url, binary)
            if req_url is not fullurl:
                for h, v in fullurl.headers.items():
                    assert isinstance(h, binary)
                    assert isinstance(v, binary)
                    headers[h.decode('utf-8').lower()] = v
        else:
            assert isinstance(req_url, text)
            if req_url is not fullurl:
                for h, v in fullurl.headers.items():
                    assert isinstance(h, text)
                    assert isinstance(v, binary)  # значение всегда binary
                    headers[h.lower()] = v


        assert data is None or isinstance(data, binary)
        assert timeout is None or isinstance(timeout, (int, float))

        # Потестировали, а дальше проще с юникодом работать
        if PY2:
            req_url = req_url.decode('utf-8')

        # Перехват запроса при необходимости, можно его параметры assert'ить здесь
        for url, func in form_interceptors.items():
            if req_url != url and req_url != api.http_host + url:
                continue
            ctype = headers['content-type'].decode('utf-8')
            if ctype.startswith('multipart/form-data;'):
                pdict = cgi.parse_header(headers['content-type'] if PY2 else ctype)[1]
                data = cgi.parse_multipart(BytesIO(data), {'boundary': pdict['boundary'].encode('utf-8')})
            else:
                data = urlparse.parse_qs(data.decode('utf-8'))
            func(data, headers)
            break

        for url, func in interceptors.items():
            if req_url == url or req_url == api.http_host + url:
                func(data, headers)
                break

        # Ищем ответ на запрос
        for url, x in list(current_mocks.items()) + list(mocks.items()):
            result_path, optparams = x
            if url.startswith('/'):
                url = api.http_host + url
            if req_url == url:
                # Отвечаем, если нашёлся
                return build_response(req_url, result_path, optparams)

        # Ответ не нашёлся, отвечаем 404
        params = {'status': 404, 'status_msg': 'Not Found'}
        if '404' in mocks:
            if mocks['404'][1]:
                params.update(mocks['404'][1])
            return build_response(req_url, mocks['404'][0], params)
        else:
            return build_response(req_url, '404.html', params)

    def send_request(self, *args, **kwargs):
        self.opener.open = self.test_open
        self.noredir.open = self.test_open
        return super(UserTest, self).send_request(*args, **kwargs)
