#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

from __future__ import unicode_literals

import time
import json
from io import BytesIO

import pytest
import tabun_api as api
from tabun_api.compat import text, binary

from testutil import UserTest, load_file, form_intercept, set_mock, user, assert_data


def test_get_profile(user, set_mock):
    set_mock({'/profile/test/': 'profile.html'})
    profile = user.get_profile('test')

    assert profile.user_id == 666
    assert profile.username == 'test'
    assert profile.realname == 'Фамилия Имя'
    assert profile.skill == 777.77
    assert profile.rating == 666.66
    assert profile.userpic == '//cdn.everypony.ru/storage/01/54/04/2014/02/28/avatar_100x100.png'
    assert profile.foto == '//cdn.everypony.ru/storage/01/54/04/2014/02/28/236ad9.jpg'
    assert profile.gender is None  # TODO: more tests
    assert time.strftime('%Y-%m-%d', profile.birthday) == '1971-02-02'
    assert time.strftime('%Y-%m-%d %H:%M', profile.registered) == '2012-03-07 03:15'
    assert time.strftime('%Y-%m-%d %H:%M', profile.last_activity) == '2016-05-22 20:30'  # TODO: can be None
    assert frozenset(profile.blogs) == frozenset(('owner', 'admin', 'moderator', 'member'))
    assert profile.blogs['owner'] == []
    assert profile.blogs['admin'] == [('news', 'Срочно в номер')]
    assert profile.blogs['moderator'] == []
    assert profile.blogs['member'] == [('shipping', 'Все о шиппинге'), ('RPG', 'РПГ7. Воюем, живем, любим.'), ('borderline', 'На грани')]
    assert profile.description is not None
    assert profile.raw_description == 'Обо мне. Сломанный код: <a href="'
    assert profile.rating_vote_count == 37
    assert profile.counts == {
        'comments': None,
        'favourites': 0,
        'favourites_comments': None,
        'favourites_posts': None,
        'friends': 3,
        'notes': None,
        'posts': None,
        'publications': 8697,
    }
    assert profile.full is True

    assert profile.contacts == [
        ('phone', None, '79001234567'),
        ('mail', 'mailto:почта@example.com', 'почта@example.com'),
        ('skype', 'skype:скайп', 'скайп'),
        ('icq', 'http://www.icq.com/people/about_me.php?uin=7777777', '7777777'),
        ('www', 'http://президент.рф', 'президент.рф'),
        ('twitter', 'http://twitter.com/твиттер/', 'твиттер'),
        ('facebook', 'http://facebook.com/фейсбук', 'фейсбук'),
        ('vkontakte', 'http://vk.com/вк', 'вк'),
        ('odnoklassniki', 'http://www.odnoklassniki.ru/profile/ок/', 'ок'),
    ]

    assert profile.context['http_host'] == 'https://tabun.everypony.ru'
    assert profile.context['url'] == 'https://tabun.everypony.ru/profile/test/'
    assert profile.context['can_vote'] is False
    assert profile.context['vote_value'] == 1
    assert profile.context['username'] == 'test'  # Да, я прописал голос за самого себя :D
    assert profile.context['note'] == '< > & " \'\ntest'
    assert profile.context['can_edit_note'] is True


def test_get_profile_topics(user, set_mock):
    set_mock({'/profile/test/created/topics/': 'profile_topics.html'})
    profile = user.get_profile(url='/profile/test/created/topics/')

    assert profile.user_id == 666
    assert profile.username == 'test'
    assert profile.realname == 'Фамилия Имя'
    assert profile.skill == 777.77
    assert profile.rating == 666.66
    assert profile.userpic is None
    assert profile.foto == '//cdn.everypony.ru/storage/01/54/04/2014/02/28/236ad9.jpg'
    assert profile.gender is None
    assert profile.birthday is None
    assert profile.registered is None
    assert profile.last_activity is None
    assert frozenset(profile.blogs) == frozenset(('owner', 'admin', 'moderator', 'member'))
    assert profile.blogs['owner'] == []
    assert profile.blogs['admin'] == []
    assert profile.blogs['moderator'] == []
    assert profile.blogs['member'] == []
    assert profile.description is None
    assert profile.raw_description is None
    assert profile.rating_vote_count == 37
    assert profile.counts == {
        'comments': 8696,
        'favourites': 0,
        'favourites_comments': None,
        'favourites_posts': None,
        'friends': 3,
        'notes': 0,
        'posts': 1,
        'publications': 8697,
    }
    assert profile.full is False

    assert profile.contacts is None

    assert profile.context['http_host'] == 'https://tabun.everypony.ru'
    assert profile.context['url'] == 'https://tabun.everypony.ru/profile/test/created/topics/'
    assert profile.context['can_vote'] is False  # А здесь я прописал vote-nobuttons
    assert profile.context['vote_value'] is None
    assert profile.context['username'] == 'test'
    assert profile.context['note'] == '< > & " \'\ntest'
    assert profile.context['can_edit_note'] is True
