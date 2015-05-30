#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os
import urllib2
from StringIO import StringIO as BytesIO
from httplib import HTTPMessage

import pytest

import tabun_api as api

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
    'FOOTER': 'footer.html'
}

interceptors = {}
current_mocks = {}

mocks = {
    '/': ('index.html', None),
    '/blog/132085.html': ('132085.html', None),
    '/comments/': ('comments.html', None)
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
        current_mocks[key] = ((value, None) if isinstance(value, basestring) else value)


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
    for metakey, key in [(b'%AUTH1%', b'AUTH1_'), (b'%AUTH2%', b'AUTH2_')]:
        if metakey not in ignorekeys and metakey in data:
            key = (key + b'GUEST') if guest_mode else (key + b'AUTHORIZED')
            tname = templates[key]
            data = data.replace(metakey, load_file(tname, ignorekeys + (key,)))

    # Пародируем шаблонизатор и включаем другие файлы в шаблон
    for key, tname in templates.items():
        key = b'%' + key.encode('utf-8') + b'%'
        if key not in ignorekeys and key in data:
            data = data.replace(key, load_file(tname, ignorekeys + (key,)))

    return data


def build_response(req_url, result_path, optparams=None):
    # Параметры ответа по умолчанию
    params = {
        'status': 200,
        'status_msg': 'OK',
        'headers': {
            'Content-Type': 'text/html; charset=utf-8',
            'Set-Cookie': [
                'PHPSESSID=abcdef9876543210abcdef9876543210; path=/',
                'LIVESTREET_SECURITY_KEY=0123456789abcdef0123456789abcdef; expires=Thu, 04-Jun-2015 23:59:59 GMT; Max-Age=604800; path=/; httponly'
            ]},
        'url': req_url
    }
    # Параметры, переданные тестом
    if optparams:
        optparams = optparams.copy()
        params['headers'].update(optparams.pop('headers', {}))
        params.update(optparams)

    # Само содержимое подделываемого ответа на HTTP-запрос
    fp = BytesIO(load_file(result_path) if result_path else params.get('data', ''))

    # Собираем HTTP-заголовки
    raw_headers = ''
    for header, value in params['headers'].items():
        raw_headers += header + ': '
        if isinstance(value, (tuple, list)):
            raw_headers += ('\r\n' + header + ': ').join(value)
        else:
            raw_headers += value
        raw_headers += '\r\n'
    headers = HTTPMessage(BytesIO(raw_headers.encode('utf-8')))

    # Для некоторых ошибок нужно сгенерировать исключение
    if (params['status'] >= 500 or params['status'] in (404,)) and not params.get('noexc'):
        raise urllib2.HTTPError(params['url'], params['status'], params['status_msg'], headers, fp)

    # Собираем ответ на HTTP-запрос
    resp = urllib2.addinfourl(fp, headers, params['url'])
    resp.code = params['status']
    resp.msg = params['status_msg']
    return resp


class UserTest(api.User):
    def urlopen(self, url, data=None, headers={}, redir=True, nowait=False, with_cookies=True, timeout=None):
        # TODO: заменить эту функцию на send_request
        # собираем urllib2.Request для проверки, что там ничего не упадёт
        self.build_request(url, data, headers, with_cookies)

        # Нормализуем url для поиска
        req_url = url.get_full_url() if isinstance(url, urllib2.Request) else url
        if req_url.startswith('/'):
            req_url = api.http_host + req_url

        # Перехват запроса при необходимости
        for url, func in interceptors.items():
            if req_url == url or req_url == api.http_host + url:
                func(url, data, headers)
                break

        # Ищем ответ на запрос
        for url, (result_path, optparams) in current_mocks.items() + mocks.items():
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
