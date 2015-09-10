#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

from __future__ import unicode_literals

import time
import json
from io import BytesIO

import pytest
import tabun_api as api
from tabun_api.compat import text

from testutil import UserTest, load_file, form_intercept, set_mock, user


def test_get_posts_data_ok(user):
    post_data = json.loads(load_file('index_posts.json', template=False).decode('utf-8'))
    posts = reversed(user.get_posts('/'))

    for data, post in zip(post_data, posts):
        assert post.post_id == data['post_id']

        for key, value in data.items():
            if key == 'time':
                assert time.strftime("%Y-%m-%d %H:%M:%S", post.time) == value
            elif key != "post_id":
                assert getattr(post, key) == value


def test_get_posts_profile_data_ok(user, set_mock):
    set_mock({'/profile/test/created/topics/': 'profile_topics.html'})

    post_data = json.loads(load_file('profile_topics.json', template=False).decode('utf-8'))
    posts = reversed(user.get_posts('/profile/test/created/topics/'))

    for data, post in zip(post_data, posts):
        assert post.post_id == data['post_id']

        for key, value in data.items():
            if key == 'time':
                assert time.strftime("%Y-%m-%d %H:%M:%S", post.time) == value
            elif key != "post_id":
                assert getattr(post, key) == value


def test_get_posts_types_ok(user):
    posts = reversed(user.get_posts('/'))
    for post in posts:
        assert isinstance(post.author, text)
        assert post.blog is None or isinstance(post.blog, text)
        assert isinstance(post.blog_name, text)
        assert isinstance(post.title, text)
        assert isinstance(post.raw_body, text)
        assert isinstance(post.tags[0], text)
        assert isinstance(post.comments_count, int)
        assert isinstance(post.comments_new_count, int)


def test_get_post_ok(user):
    post = user.get_post(132085)
    assert post.post_id == 132085
    assert post.author == 'test'
    assert post.private == False
    assert post.blog is None
    assert post.draft == True
    assert time.strftime("%Y-%m-%d %H:%M:%S", post.time) == "2015-05-30 19:14:04"

    assert post.title == 'Тест'
    assert post.raw_body == '<strong>Раз</strong><br/>\n<h4>Два</h4>И ломаем вёрстку <img src="http://ya.ru/" alt="'
    assert post.tags == ["тег1", "тег2"]
    assert post.comments_count == 5
    assert post.comments_new_count == 0


def test_get_post_other_ok(user):
    post = user.get_post(138982, 'borderline')
    assert post.post_id == 138982
    assert post.author == 'test'
    assert post.private == True
    assert post.blog == 'borderline'
    assert post.draft == True
    assert time.strftime("%Y-%m-%d %H:%M:%S", post.time) == "2015-09-10 15:39:13"

    assert post.title == 'Тестирование ката'
    assert post.raw_body == '<img src="https://i.imgur.com/V3KzzyAs.png"/>Текст до ката<br/>\n<a></a> <br/>\nТекст после ката<img src="https://i.imgur.com/NAg929K.jpg"/>'
    assert post.tags == ["Луна", "аликорны", "новость"]
    assert post.comments_count == 0
    assert post.comments_new_count == 0


def test_get_post_other_blog_1(set_mock, user):
    set_mock({'/blog/news/132085.html': ('132085.html', {'url': '/blog/132085.html'})})
    assert user.get_post(132085, 'news').blog is None


def test_get_post_other_blog_2(set_mock, user):
    set_mock({'/blog/blog/132085.html': ('132085.html', {'url': '/blog/132085.html'})})
    assert user.get_post(132085, 'blog').blog is None


@pytest.mark.parametrize("blog_id,blog,result_url,draft,tags", [
    (6, 'news', 'http://tabun.everypony.ru/blog/news/1.html', False, ['Т2', 'Т3']),
    (6, 'news', 'http://tabun.everypony.ru/blog/news/1.html', False, ['Т2, Т3']),
    (None, None, 'http://tabun.everypony.ru/blog/1.html', True, ['Т2', 'Т3'])
])
def test_add_post_ok(form_intercept, set_mock, user, blog_id, blog, result_url, draft, tags):
    set_mock({
        '/topic/add/': (None, {
            'headers': {'location': result_url},
            'status': 302, 'status_msg': 'Found'
        }
    )})
    @form_intercept('/topic/add/')
    def topic_add(data, headers):
        assert data.get('blog_id') == [text(blog_id if blog_id is not None else 0).encode('utf-8')]
        assert data.get('security_ls_key') == [b'0123456789abcdef0123456789abcdef']
        assert data.get('topic_title') == ['Т0'.encode('utf-8')]
        assert data.get('topic_text') == ['Б1'.encode('utf-8')]
        assert data.get('topic_tags') == ['Т2, Т3'.encode('utf-8')]
        if draft:
            assert data.get('submit_topic_save') == ['Сохранить в черновиках'.encode('utf-8')]
        else:
            assert data.get('submit_topic_publish') == ['Опубликовать'.encode('utf-8')]

    result = user.add_post(blog_id, 'Т0', 'Б1', tags, draft)
    assert result == (blog, 1)


def test_add_post_error(set_mock, user):
    set_mock({'/topic/add/': 'topic_add_error.html'})
    with pytest.raises(api.TabunResultError) as excinfo:
        user.add_post(None, '', '', [])
    assert excinfo.value.message == 'Поле Заголовок слишком короткое (минимально допустимо 2 символов)'

# TODO: rss
