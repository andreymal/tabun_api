#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

from __future__ import unicode_literals

import pytest
import tabun_api as api
from tabun_api.compat import PY2

import testutil
from testutil import UserTest, form_intercept, set_mock, as_guest, user


def test_user_preloaded_cookies(set_mock):
    set_mock({'/': ('404.html', {'status': 404, 'status_msg': 'Not Found'})})
    phpsessid = 'abcdef9876543210abcdef9876543210'
    security_ls_key = '0123456789abcdef0123456789abcdef'
    key = '00000000000000000000000000000000'
    user = UserTest(phpsessid=phpsessid, security_ls_key=security_ls_key, key=key)
    assert user.username is None
    assert user.phpsessid == phpsessid
    assert user.security_ls_key == security_ls_key
    assert user.key == key


@pytest.mark.parametrize("session_id,security_ls_key,key", [
    ('abcdef9876543210abcdef9876543210', '0123456789abcdef0123456789abcdef', None),
    ('abcdef9876543210abcdef9876543210', None, '00000000000000000000000000000000'),
    ('abcdef9876543210abcdef9876543210', None, None)
])
def test_user_partially_preloaded_cookies(session_id, security_ls_key, key):
    user = UserTest(phpsessid=session_id, security_ls_key=security_ls_key, key=key)
    assert user.username == None if security_ls_key else 'test'
    assert user.phpsessid == session_id
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key in (None, '00000000000000000000000000000000')

    assert user.update_userinfo(user.urlopen('/').read()) == 'test'
    assert user.phpsessid == session_id
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key in (None, '00000000000000000000000000000000')


def test_user_preloaded_cookies_and_login(set_mock):
    set_mock({'/': ('404.html', {'status': 404, 'status_msg': 'Not Found'})})
    user = UserTest('test', phpsessid='abcdef9876543210abcdef9876543210', security_ls_key='0123456789abcdef0123456789abcdef')
    assert user.username == 'test'
    assert user.phpsessid == 'abcdef9876543210abcdef9876543210'
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key is None


def test_session_id_guest(as_guest, user):
    assert user.phpsessid == 'abcdef9876543210abcdef9876543210'


def test_session_id_authorized(user):
    assert user.phpsessid == 'abcdef9876543210abcdef9876543210'


def test_session_id_renamed_guest(set_mock, as_guest):
    class OtherTestUser(UserTest):
        session_cookie_name = 'PHPSESSID'
    set_mock({'/': (None, {'headers': {'Set-Cookie': ['PHPSESSID=abcdef9876543210abcdef9876543210; path=/']}})})

    user = OtherTestUser()
    assert user.phpsessid == 'abcdef9876543210abcdef9876543210'


def test_session_id_renamed_authorized(set_mock):
    class OtherTestUser(UserTest):
        session_cookie_name = 'PHPSESSID'
    set_mock({'/': (None, {'headers': {'Set-Cookie': ['PHPSESSID=abcdef9876543210abcdef9876543210; path=/']}})})

    user = OtherTestUser()
    assert user.phpsessid == 'abcdef9876543210abcdef9876543210'


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


def test_init_proxy_ok():
    if not PY2:
        with pytest.raises(NotImplementedError):
            UserTest(proxy='socks5,localhost,9999')
        return
    assert UserTest(proxy='socks5,localhost,9999').proxy == ['socks5', 'localhost', 9999]
    assert UserTest(proxy='socks4,localhost,9999').proxy == ['socks4', 'localhost', 9999]


def test_init_proxy_from_setenv():
    import os
    old_getenv = os.getenv
    def getenv(*args, **kwargs):
        if args and args[0] == 'TABUN_API_PROXY':
            return 'socks5,localhost,8888'
        return old_getenv(*args, **kwargs)
    os.getenv = getenv

    try:
        if not PY2:
            with pytest.raises(NotImplementedError):
                UserTest()
            return

        assert UserTest().proxy == ['socks5', 'localhost', 8888]
    finally:
        os.getenv = old_getenv

def test_init_proxy_unknown():
    with pytest.raises(NotImplementedError):
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
        assert req.get_full_url() == b'http://tabun.everypony.ru/blog/2.html'
    else:
        assert req.get_full_url() == 'http://tabun.everypony.ru/blog/2.html'
    assert b'TABUNSESSIONID=abcdef9876543210abcdef9876543210' in req.headers[str('Cookie')]


def test_build_request_internal_other_session_cookie(user):
    user.session_cookie_name = 'PHPSESSID'
    req = user.build_request('/blog/2.html')
    if PY2:
        assert req.get_full_url() == b'http://tabun.everypony.ru/blog/2.html'
    else:
        assert req.get_full_url() == 'http://tabun.everypony.ru/blog/2.html'
    assert b'PHPSESSID=abcdef9876543210abcdef9876543210' in req.headers[str('Cookie')]


def test_build_request_external(user):
    req = user.build_request(b'https://imgur.com/', with_cookies=False)
    if PY2:
        assert req.get_full_url() == b'https://imgur.com/'
    else:
        assert req.get_full_url() == 'https://imgur.com/'
    assert str('Cookie') not in req.headers.keys()
