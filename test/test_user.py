#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

import pytest

import tabun_api as api

import testutil
from testutil import UserTest, set_mock, as_guest, user


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


@pytest.mark.parametrize("phpsessid,security_ls_key,key", [
    ('abcdef9876543210abcdef9876543210', '0123456789abcdef0123456789abcdef', None),
    ('abcdef9876543210abcdef9876543210', None, '00000000000000000000000000000000'),
    ('abcdef9876543210abcdef9876543210', None, None)
])
def test_user_partially_preloaded_cookies(phpsessid, security_ls_key, key):
    user = UserTest(phpsessid=phpsessid, security_ls_key=security_ls_key, key=key)
    assert user.username == None if security_ls_key else 'test'
    assert user.phpsessid == phpsessid
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key in (None, '00000000000000000000000000000000')

    assert user.update_userinfo(user.urlopen('/').read()) == 'test'
    assert user.phpsessid == phpsessid
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key in (None, '00000000000000000000000000000000')


def test_user_preloaded_cookies_and_login(set_mock):
    set_mock({'/': ('404.html', {'status': 404, 'status_msg': 'Not Found'})})
    user = UserTest('test', phpsessid='abcdef9876543210abcdef9876543210', security_ls_key='0123456789abcdef0123456789abcdef')
    assert user.username == 'test'
    assert user.phpsessid == 'abcdef9876543210abcdef9876543210'
    assert user.security_ls_key == '0123456789abcdef0123456789abcdef'
    assert user.key is None


def test_phpsessid_guest(as_guest, user):
    assert user.phpsessid == 'abcdef9876543210abcdef9876543210'


def test_phpsessid_authorized(user):
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
    assert UserTest(proxy='socks5,localhost,9999').proxy == ['socks5', 'localhost', 9999]


def test_init_proxy_unknown():
    with pytest.raises(NotImplementedError):
        UserTest(proxy='blablabla,localhost,9999')
