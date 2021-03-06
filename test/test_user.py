#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

from __future__ import unicode_literals

import pytest
import tabun_api as api
from tabun_api.compat import PY2

import testutil
from testutil import UserTest, intercept, form_intercept, set_mock, as_guest, user


def test_user_preloaded_cookies(set_mock):
    set_mock({'/': ('404.html', {'status': 404, 'status_msg': 'Not Found'})})
    session_id = 'abcdef9876543210abcdef9876543210'
    security_ls_key = '0123456789abcdef0123456789abcdef'
    key = '00000000000000000000000000000000'
    user = UserTest(session_id=session_id, security_ls_key=security_ls_key, key=key)
    assert user.username is None
    assert user.session_id == session_id
    assert user.security_ls_key == security_ls_key
    assert user.key == key


@pytest.mark.parametrize("session_id,security_ls_key,key", [
    ('abcdef9876543210abcdef9876543210', '0123456789abcdef0123456789abcdef', None),
    ('abcdef9876543210abcdef9876543210', None, '00000000000000000000000000000000'),
    ('abcdef9876543210abcdef9876543210', None, None)
])
def test_user_partially_preloaded_cookies(session_id, security_ls_key, key):
    user = UserTest(session_id=session_id, security_ls_key=security_ls_key, key=key)
    assert user.username is None if security_ls_key else 'test'
    assert user.session_id == session_id
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key in (None, '00000000000000000000000000000000')

    assert user.update_userinfo(user.urlopen('/').read()) == 'test'
    assert user.session_id == session_id
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key in (None, '00000000000000000000000000000000')


def test_user_preloaded_cookies_and_login(set_mock):
    set_mock({'/': ('404.html', {'status': 404, 'status_msg': 'Not Found'})})
    user = UserTest('test', session_id='abcdef9876543210abcdef9876543210', security_ls_key='0123456789abcdef0123456789abcdef')
    assert user.username == 'test'
    assert user.session_id == 'abcdef9876543210abcdef9876543210'
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key is None


def test_session_id_guest(as_guest, user):
    assert user.session_id == 'abcdef9876543210abcdef9876543210'


def test_session_id_authorized(user):
    assert user.session_id == 'abcdef9876543210abcdef9876543210'


def test_session_id_renamed_guest(set_mock, as_guest):
    extra = {'headers': {'Set-Cookie': ['PHPSESSID=abcdef9876543210abcdef9876543210; path=/']}}
    set_mock({
        '/': ('index.html', extra),
        '/login/': ('index.html', extra),
    })

    user = UserTest(session_cookie_name='PHPSESSID')
    assert user.session_id == 'abcdef9876543210abcdef9876543210'


def test_session_id_renamed_authorized(set_mock):
    extra = {'headers': {'Set-Cookie': ['PHPSESSID=abcdef9876543210abcdef9876543210; path=/']}}
    set_mock({
        '/': ('index.html', extra),
        '/login/': ('index.html', extra),
    })

    user = UserTest(session_cookie_name='PHPSESSID')
    assert user.session_id == 'abcdef9876543210abcdef9876543210'


def test_ls_key_guest(as_guest, user):
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'


def test_ls_key_authorized(user):
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'


def test_userinfo_guest(as_guest, user):
    assert user.username is None
    assert user.rating is None
    assert user.skill is None


def test_userinfo_authorized(user):
    assert user.username == 'test'
    assert user.rating == 666.66
    assert user.skill == 777.77


def test_login_request(set_mock, form_intercept, as_guest, user):
    set_mock({'/login/ajax-login': 'ajax_login_ok.json'})
    @form_intercept('/login/ajax-login')
    def login(data, headers):
        assert data.get('login') == ['test']
        assert data.get('password') == ['123456']
        assert data.get('security_ls_key') == [user.security_ls_key]
    user.login('test', '123456')


def test_login_ok(set_mock, as_guest, user):
    set_mock({'/login/ajax-login': 'ajax_login_ok.json'})
    assert user.username is None
    assert user.login('test', '123456') is None
    testutil.guest_mode = False
    assert user.update_userinfo(user.urlopen('/').read()) == 'test'
    assert user.username == 'test'


def test_login_fail(set_mock, as_guest, user):
    set_mock({'/login/ajax-login': 'ajax_login_fail.json'})
    assert user.username is None
    with pytest.raises(api.TabunResultError):
        user.login('test', '123456')
    assert user.username is None
    assert user.update_userinfo(user.urlopen('/').read()) is None
    assert user.username is None


def test_login_init_ok(set_mock, as_guest):
    set_mock({'/login/ajax-login': 'ajax_login_ok.json'})
    user = UserTest('test', '123456')
    testutil.guest_mode = False
    assert user.update_userinfo(user.urlopen('/').read()) == 'test'
    assert user.username == 'test'


def test_login_init_fail(set_mock, as_guest):
    set_mock({'/login/ajax-login': 'ajax_login_fail.json'})
    with pytest.raises(api.TabunResultError):
        UserTest('test', '123456')


def test_logout_auto(set_mock, as_guest, user):
    testutil.guest_mode = False
    assert user.update_userinfo(user.urlopen('/').read()) == 'test'
    assert user.username == 'test'

    testutil.guest_mode = True
    assert user.update_userinfo(user.urlopen('/').read()) is None
    assert user.username is None
    assert user.rating is None
    assert user.skill is None


def test_init_proxy_legacy_ok():
    assert UserTest(proxy='socks5,localhost,9999').proxy == 'socks5://localhost:9999'
    assert UserTest(proxy='socks4,localhost,9999').proxy == 'socks4://localhost:9999'


def test_init_proxy_ok():
    assert UserTest(proxy='socks5://localhost:9999').proxy == 'socks5://localhost:9999'
    assert UserTest(proxy='socks4://localhost:9999').proxy == 'socks4://localhost:9999'
    assert UserTest(proxy='http://localhost:9999').proxy == 'http://localhost:9999'


def test_init_proxy_from_env():
    import os
    old_getenv = os.getenv
    def getenv(*args, **kwargs):
        if args and args[0] == 'TABUN_API_PROXY':
            return 'socks5://localhost:8888'
        return old_getenv(*args, **kwargs)
    os.getenv = getenv

    try:
        assert UserTest().proxy == 'socks5://localhost:8888'
    finally:
        os.getenv = old_getenv


def test_init_proxy_ignore_env():
    import os
    old_getenv = os.getenv
    def getenv(*args, **kwargs):
        if args and args[0] == 'TABUN_API_PROXY':
            return 'socks5://localhost:8888'
        return old_getenv(*args, **kwargs)
    os.getenv = getenv

    try:
        assert UserTest(proxy='').proxy is None
    finally:
        os.getenv = old_getenv


def test_init_proxy_unknown():
    with pytest.raises(ValueError):
        UserTest(proxy='blablabla,localhost,9999')


def test_check_login(user):
    user.security_ls_key = None
    with pytest.raises(api.TabunError):
        user.check_login()


def test_ajax_hacking_attemp(set_mock, user):
    set_mock({'/ajax/': (None, {'data': b'Hacking attemp!'})})
    with pytest.raises(api.TabunResultError) as excinfo:
        user.ajax('/ajax/', {'a': 5})
    assert excinfo.value.message == 'Hacking attemp!'


def test_login_hacking_attemp(set_mock, user):
    set_mock({'/login/ajax-login': (None, {'data': b'Hacking attemp!'})})
    with pytest.raises(api.TabunResultError) as excinfo:
        user.login('test', '123456')
    assert excinfo.value.message == 'Hacking attemp!'


def test_build_request_internal(user):
    req = user.build_request('/blog/2.html')
    if PY2:
        assert req.get_full_url() == b'https://tabun.everypony.ru/blog/2.html'
    else:
        assert req.get_full_url() == 'https://tabun.everypony.ru/blog/2.html'
    assert b'TABUNSESSIONID=abcdef9876543210abcdef9876543210' in req.headers[str('Cookie')]


def test_build_request_internal_other_session_cookie(user):
    user.session_cookie_name = 'PHPSESSID'
    req = user.build_request('/blog/2.html')
    if PY2:
        assert req.get_full_url() == b'https://tabun.everypony.ru/blog/2.html'
    else:
        assert req.get_full_url() == 'https://tabun.everypony.ru/blog/2.html'
    assert b'PHPSESSID=abcdef9876543210abcdef9876543210' in req.headers[str('Cookie')]


def test_build_request_external(user):
    req = user.build_request(b'https://imgur.com/', with_cookies=False)
    if PY2:
        assert req.get_full_url() == b'https://imgur.com/'
    else:
        assert req.get_full_url() == 'https://imgur.com/'
    assert str('Cookie') not in req.headers.keys()


def test_build_request_nonascii(user):
    req = user.build_request('/blog/©ы\u007f')
    if PY2:
        assert req.get_full_url() == b'https://tabun.everypony.ru/blog/%C2%A9%D1%8B%7F'
    else:
        assert req.get_full_url() == 'https://tabun.everypony.ru/blog/%C2%A9%D1%8B%7F'


def test_build_request_invalid(user):
    with pytest.raises(ValueError):
        user.build_request(b'file:///etc/passwd')


def test_send_request_without_interval(user):
    import time

    now = [100]
    sleeps = []
    def sleep(n):
        sleeps.append(n)
        now[0] += n
        now[0] += 1  # всякие техничские задержки
    def get_time():
        return now[0]

    old_sleep = time.sleep
    old_time = time.time
    time.sleep = sleep
    time.time = get_time

    try:
        user.urlopen('/')
        assert sleeps == []
        assert user.last_query_time == now[0]

        now[0] += 2
        user.urlopen('/comments/', nowait=True)
        assert sleeps == []
        assert user.last_query_time == now[0]

        now[0] += 2
        user.urlopen('/stream/all/')
        assert sleeps == []
        assert user.last_query_time == now[0]

        now[0] += 100
        user.urlopen('/')
        assert sleeps == []
        assert user.last_query_time == now[0]
    finally:
        time.sleep = old_sleep
        time.time = old_time


def test_send_request_with_interval(user):
    user.query_interval = 5

    import time

    now = [100]
    sleeps = []
    def sleep(n):
        sleeps.append(n)
        now[0] += n
        now[0] += 1  # имитация технических задержек и неточности time.time()
    def get_time():
        return now[0]

    old_sleep = time.sleep
    old_time = time.time
    time.sleep = sleep
    time.time = get_time

    try:
        user.urlopen('/')
        assert sleeps == []
        assert user.last_query_time == now[0]

        now[0] += 2  # 100 + 2 = 102
        user.urlopen('/comments/')  # 102 + (5 - 2) + 1 = 106
        assert sleeps == [3]
        assert user.last_query_time == now[0] - 1  # встроена компенсация технических задержек

        now[0] += 1  # 106 + 1 = 107
        user.urlopen('/', nowait=True)  # 107 + 0 = 107
        assert sleeps == [3]
        assert user.last_query_time == now[0]

        now[0] += 1  # 107 + 1 = 108
        user.urlopen('/stream/all/')  # 108 + (5 - 1) + 1 = 113 (предыдущий запрос сбросил last_query_time)
        assert sleeps == [3, 4]
        assert user.last_query_time == now[0] - 1

        now[0] += 100  # 113 + 100 = 213
        user.urlopen('/')  # 213 + 0 = 213
        assert sleeps == [3, 4]
        assert user.last_query_time == now[0]
    finally:
        time.sleep = old_sleep
        time.time = old_time


def _get_cf_data(set_cookie_1=True, set_cookie_2=True):
    # При первом запросе CF присылает такую печеньку
    cookvalue1 = 'd232e4cdfaa674c8dad1b0e9a5c34b6a71471775125'
    cook1 = (
        '__cfduid=d232e4cdfaa674c8dad1b0e9a5c34b6a71471775125; '
        'expires=Mon, 21-Aug-17 10:25:25 GMT; path=/; '
        'domain=.everypony.ru; HttpOnly'
    )
    # и такой ответ в целом
    headers1 = {'CF-RAY': '2d5d6189365c2bfa'}
    if set_cookie_1:
        headers1 ['Set-Cookie'] = cook1
    cf_mock = ('cf_503.html', {'status': 503, 'status_msg': 'Service Unavailable', 'headers': headers1})

    # Браузер (который мы подделываем, ха-ха), должен отправить GET-запрос сюда
    answer_url = '/cdn-cgi/l/chk_jschl?jschl_vc=cf66aa3658a6bbd1b9b5d0df9525e107&pass=1471775129.953-62xuaff3yZ&jschl_answer=1773544653'

    # Если всё хорошо, CF пришлёт такую печеньку
    cookvalue2 = '7acca457068bfa7bf6a54c141d89346bd7799b64-1471775130-10800'
    cook2 = (
        'cf_clearance=7acca457068bfa7bf6a54c141d89346bd7799b64-1471775130-10800; '
        'expires=Sun, 21-Aug-16 14:25:30 GMT; path=/; '
        'domain=.everypony.ru; HttpOnly'
    )
    # и перенаправит уже на нормальную страницу
    headers2 = {'Set-Cookie': cook2} if set_cookie_2 else {}
    cf_mock_solved = (None, {'data': b'', 'status': 302 , 'status_msg': 'Moved Temporarily', 'headers': headers2})

    return {
        'cook1': cook1,
        'cookvalue1': cookvalue1,
        'cf_mock': cf_mock,
        'answer_url': answer_url,
        'cookvalue2': cookvalue2,
        'cook2': cook2,
        'cf_mock_solved': cf_mock_solved,
    }


def test_cloudflare_solution_ok(set_mock, as_guest, intercept):
    cfdata = _get_cf_data()

    set_mock({
        '/': cfdata['cf_mock'],
        '/login/': cfdata['cf_mock'],
        cfdata['answer_url']: cfdata['cf_mock_solved'],
    })

    # Проверка того, что реализация не делает ничего лишнего
    calls = {'page': 0, 'solve': 0}

    @intercept('/')
    @intercept('/login/')
    def get_page(data, headers):
        calls['page'] += 1

    @intercept(cfdata['answer_url'])
    def cf_solve(data, headers):
        calls['solve'] += 1
        set_mock({
            '/': 'index.html',
            '/login/': 'login.html',
        })

    user = UserTest(avoid_cf=True)

    # Пытаемся открыть Табун, потом спим 4 секунды, решаем задачку CF и снова пытаемся
    assert calls == {'page': 2, 'solve': 1}
    assert user.sleeps == [1, 4.0]

    assert user.extra_cookies == {
        '__cfduid': cfdata['cookvalue1'],
        'cf_clearance': cfdata['cookvalue2'],
    }
    assert user.session_id == 'abcdef9876543210abcdef9876543210'
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'


def test_cloudflare_solution_ok_again(set_mock, as_guest, intercept):
    # Отличие от предыдущего теста в том, что печеньки уже стоят заранее
    cfdata = _get_cf_data()

    set_mock({
        '/': cfdata['cf_mock'],
        '/login/': cfdata['cf_mock'],
        cfdata['answer_url']: cfdata['cf_mock_solved'],
    })

    calls = {'page': 0, 'solve': 0}

    @intercept('/')
    @intercept('/login/')
    def get_page(data, headers):
        calls['page'] += 1

    @intercept(cfdata['answer_url'])
    def cf_solve(data, headers):
        calls['solve'] += 1
        set_mock({
            '/': 'index.html',
            '/login/': 'login.html',
        })

    user = UserTest(security_ls_key='N/A', session_id='abcdef9876543210abcdef9876543210', avoid_cf=True)
    user.extra_cookies.update({
        '__cfduid': cfdata['cookvalue1'],
        'cf_clearance': 'foobarblablablathisisoldcookie',
    })

    resp = user.urlopen('/')
    assert resp.code == 200
    user.update_userinfo(resp.read())

    assert calls == {'page': 2, 'solve': 1}
    assert user.sleeps == [1, 4.0]

    assert user.extra_cookies == {
        '__cfduid': cfdata['cookvalue1'],
        'cf_clearance': cfdata['cookvalue2'],
    }
    assert user.session_id == 'abcdef9876543210abcdef9876543210'
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'


def test_cloudflare_solution_fail_infinity(set_mock, as_guest, intercept):
    cfdata = _get_cf_data()

    set_mock({
        '/': cfdata['cf_mock'],
        '/login/': cfdata['cf_mock'],
        cfdata['answer_url']: cfdata['cf_mock'],  # В сравнении с предыдущим тестом облом вот тут
    })

    calls = {'page': 0, 'solve': 0}

    @intercept('/')
    @intercept('/login/')
    def get_page(data, headers):
        calls['page'] += 1

    @intercept(cfdata['answer_url'])
    def cf_solve(data, headers):
        calls['solve'] += 1
        # И вот тут

    user = UserTest(security_ls_key='N/A', session_id='N/A', avoid_cf=True)

    with pytest.raises(api.TabunError) as excinfo:
        user.urlread('/')
    assert excinfo.value.code == 503

    assert calls == {'page': 10, 'solve': 9}
    assert user.sleeps == [9, 4.0 * 9]

    assert user.extra_cookies == {'__cfduid': cfdata['cookvalue1']}
    assert user.session_id == 'N/A'
    assert user.security_ls_key == 'N/A'
