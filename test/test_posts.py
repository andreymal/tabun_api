#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

import cgi
import time
import json
from StringIO import StringIO

import pytest
import tabun_api as api

from testutil import UserTest, load_file, intercept, set_mock, user


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


def test_get_posts_types_ok(user):
    posts = reversed(user.get_posts('/'))
    for post in posts:
        assert isinstance(post.author, unicode)
        assert post.blog is None or isinstance(post.blog, unicode)
        assert isinstance(post.blog_name, unicode)
        assert isinstance(post.title, unicode)
        assert isinstance(post.raw_body, unicode)
        assert isinstance(post.tags[0], unicode)
        assert isinstance(post.comments_count, int)
        assert isinstance(post.comments_new_count, int)


def test_get_post_ok(user):
    post = user.get_post(132085)
    assert post.post_id == 132085
    assert post.author == u'test'
    assert post.private == False
    assert post.draft == True
    assert time.strftime("%Y-%m-%d %H:%M:%S", post.time) == "2015-05-30 19:14:04"

    assert post.title == u'Тест'
    assert post.raw_body == u'<strong>Раз</strong><br/>\n<h4>Два</h4>И ломаем вёрстку <img src="http://ya.ru/" alt="'
    assert post.tags == [u"тег1", u"тег2"]
    assert post.comments_count == 5
    assert post.comments_new_count == 0


def test_get_post_other_blog_1(set_mock, user):
    set_mock({'/blog/news/132085.html': ('132085.html', {'url': '/blog/132085.html'})})
    assert user.get_post(132085, 'news').blog is None

def test_get_post_other_blog_2(set_mock, user):
    set_mock({'/blog/blog/132085.html': ('132085.html', {'url': '/blog/132085.html'})})
    assert user.get_post(132085, 'blog').blog is None


@pytest.mark.parametrize("blog_id,blog,result_url,draft,tags", [
    (6, 'news', 'http://tabun.everypony.ru/blog/news/1.html', False, [u'Т2', u'Т3']),
    (6, 'news', 'http://tabun.everypony.ru/blog/news/1.html', False, [u'Т2, Т3']),
    (None, None, 'http://tabun.everypony.ru/blog/1.html', True, [u'Т2', u'Т3'])
])
def test_add_post_ok(intercept, set_mock, user, blog_id, blog, result_url, draft, tags):
    set_mock({
        '/topic/add/': (None, {
            'headers': {'location': result_url},
            'status': 302, 'status_msg': 'Found'
        }
    )})
    @intercept('/topic/add/')
    def topic_add(url, data, headers):
        assert headers.get('content-type', '').startswith('multipart/form-data; boundary=-')
        pdict = cgi.parse_header(headers['content-type'])[1]
        data = cgi.parse_multipart(StringIO(data), pdict)

        assert data.get('blog_id') == [str(blog_id if blog_id is not None else 0)]
        assert data.get('security_ls_key') == ['0123456789abcdef0123456789abcdef']
        assert data.get('topic_title') == [u'Т0'.encode('utf-8')]
        assert data.get('topic_text') == [u'Б1'.encode('utf-8')]
        assert data.get('topic_tags') == [u'Т2, Т3'.encode('utf-8')]
        if draft:
            assert data.get('submit_topic_save') == [u'Сохранить в черновиках'.encode('utf-8')]
        else:
            assert data.get('submit_topic_publish') == [u'Опубликовать'.encode('utf-8')]

    result = user.add_post(blog_id, u'Т0', u'Б1', tags, draft)
    assert result == (blog, 1)


def test_add_post_error(intercept, set_mock, user):
    set_mock({'/topic/add/': 'topic_add_error.html'})
    with pytest.raises(api.TabunResultError) as excinfo:
        user.add_post(None, u'', u'', [])
    assert excinfo.value.message == u'Поле Заголовок слишком короткое (минимально допустимо 2 символов)'

# TODO: rss