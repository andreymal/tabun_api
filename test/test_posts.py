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

from testutil import UserTest, load_file, form_intercept, as_guest, set_mock, user, assert_data


def test_get_posts_data_ok(user):
    post_data = json.loads(load_file('index_posts.json', template=False).decode('utf-8'))
    posts = list(reversed(user.get_posts('/')))

    assert len(posts) == len(post_data)
    for data, post in zip(post_data, posts):
        assert post.post_id == data['post_id']
        assert_data(post, data)


def test_get_posts_data_ok_without_escape(user):
    def noescape(data, may_be_short=False):
        return data

    old_escape = api.utils.escape_topic_contents
    api.utils.escape_topic_contents = noescape
    try:
        post_data = json.loads(load_file('index_posts.json', template=False).decode('utf-8'))
        posts = list(reversed(user.get_posts('/')))

        assert len(posts) == len(post_data)
        for data, post in zip(post_data, posts):
            assert post.post_id == data['post_id']
            assert_data(post, data)
    finally:
        api.utils.escape_topic_contents = old_escape


def test_get_posts_profile_data_ok(user, set_mock):
    set_mock({'/profile/test/created/topics/': 'profile_topics.html'})

    post_data = json.loads(load_file('profile_topics.json', template=False).decode('utf-8'))
    posts = list(reversed(user.get_posts('/profile/test/created/topics/')))

    assert len(posts) == len(post_data)
    for data, post in zip(post_data, posts):
        assert post.post_id == data['post_id']
        assert_data(post, data)


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
        assert post.cut_text is None or isinstance(post.cut_text, text)
        assert isinstance(post.context, dict)


def test_get_posts_context_user_ok(user):
    posts = reversed(user.get_posts('/'))
    for post in posts:
        c = post.context
        assert isinstance(c['username'], text)
        assert isinstance(c['http_host'], text)
        assert isinstance(c['url'], text)
        assert isinstance(c['can_comment'], type(None))  # not available on lists
        assert isinstance(c['can_edit'], bool)
        assert isinstance(c['can_delete'], bool)
        assert isinstance(c['can_vote'], bool)
        assert isinstance(c['vote_value'], (int, type(None)))  # None is not voted
        assert isinstance(c['favourited'], bool)
        assert isinstance(c['subscribed_to_comments'], type(None))  # not available on lists
        assert isinstance(c['unread_comments_count'], int)


def test_get_posts_context_guest_ok(user, as_guest):
    posts = reversed(user.get_posts('/'))
    for post in posts:
        c = post.context
        assert isinstance(c['username'], type(None))
        assert isinstance(c['http_host'], text)
        assert isinstance(c['url'], text)
        assert isinstance(c['can_comment'], type(None))  # not available no lists
        assert isinstance(c['can_edit'], bool)
        assert isinstance(c['can_delete'], bool)
        assert isinstance(c['can_vote'], bool)
        assert isinstance(c['vote_value'], (int, type(None)))  # None is not voted
        assert isinstance(c['favourited'], bool)
        assert isinstance(c['subscribed_to_comments'], type(None))  # not available on lists
        assert isinstance(c['unread_comments_count'], int)


def test_get_post_ok(user):
    post = user.get_post(132085)
    assert post.post_id == 132085
    assert post.author == 'test'
    assert post.private is False
    assert post.blog is None
    assert post.draft is True
    assert post.short is False
    assert time.strftime("%Y-%m-%d %H:%M:%S", post.time) == "2015-05-30 19:14:04"
    assert post.utctime.strftime('%Y-%m-%d %H:%M:%S') == '2015-05-30 16:14:04'

    assert post.title == 'Тест'
    assert post.raw_body == '<strong>Раз</strong><br/>\n<h4>Два</h4>И ломаем вёрстку <img src="http://ya.ru/" alt="'
    assert post.tags == ["тег1", "тег2"]
    assert post.cut_text is None
    assert post.comments_count == 5

    assert post.context['username'] == 'test'
    assert post.context['http_host'] == 'https://tabun.everypony.ru'
    assert post.context['url'] == 'https://tabun.everypony.ru/blog/132085.html'
    assert post.context['can_comment'] is True
    assert post.context['can_edit'] is True
    assert post.context['can_delete'] is True
    assert post.context['can_vote'] is False
    assert post.context['vote_value'] is None
    assert post.context['favourited'] is False
    assert post.context['subscribed_to_comments'] is True
    assert post.context['unread_comments_count'] == 0


def test_get_post_other_ok(user):
    post = user.get_post(138982, 'borderline')
    assert post.post_id == 138982
    assert post.author == 'test2'
    assert post.private is True
    assert post.blog == 'borderline'
    assert post.draft is False
    assert post.short is False
    assert time.strftime("%Y-%m-%d %H:%M:%S", post.time) == "2015-09-10 15:39:13"

    assert post.title == 'Тестирование ката'
    assert post.raw_body == '<img src="https://i.imgur.com/V3KzzyAs.png"/>Текст до ката<br/>\n<a></a> <br/>\nТекст после ката<img src="https://i.imgur.com/NAg929K.jpg"/>'
    assert post.tags == ["Луна", "аликорны", "новость"]
    assert post.comments_count == 0
    assert post.cut_text is None
    assert post.vote_count == 35
    assert post.vote_total == 36

    assert post.context['username'] == 'test'
    assert post.context['http_host'] == 'https://tabun.everypony.ru'
    assert post.context['url'] == 'https://tabun.everypony.ru/blog/borderline/138982.html'
    assert post.context['can_comment'] is False
    assert post.context['can_edit'] is False
    assert post.context['can_delete'] is False
    assert post.context['can_vote'] is False
    assert post.context['vote_value'] == 1
    assert post.context['favourited'] is True
    assert post.context['subscribed_to_comments'] is False
    assert post.context['unread_comments_count'] == 0


def test_get_post_other_blog_1(set_mock, user):
    set_mock({'/blog/news/132085.html': ('132085.html', {'url': '/blog/132085.html'})})
    assert user.get_post(132085, 'news').blog is None


def test_get_post_other_blog_2(set_mock, user):
    set_mock({'/blog/blog/132085.html': ('132085.html', {'url': '/blog/132085.html'})})
    assert user.get_post(132085, 'blog').blog is None


@pytest.mark.parametrize("blog_id,blog,result_url,draft,tags,forbid_comment", [
    (6, 'news', 'https://tabun.everypony.ru/blog/news/1.html', False, ['Т2', 'Т3'], False),
    (6, 'news', 'https://tabun.everypony.ru/blog/news/1.html', False, ['Т2, Т3'], True),
    (None, None, 'https://tabun.everypony.ru/blog/1.html', True, ['Т2', 'Т3'], False)
])
def test_add_post_ok(form_intercept, set_mock, user, blog_id, blog, result_url, draft, tags, forbid_comment):
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
        if forbid_comment:
            assert data.get('topic_forbid_comment') == [b'1']
        else:
            assert 'topic_forbid_comment' not in data

    result = user.add_post(blog_id, 'Т0', 'Б1', tags, forbid_comment, draft=draft)
    assert result == (blog, 1)


@pytest.mark.parametrize("blog_id,blog,result_url,draft,tags,forbid_comment", [
    (6, 'news', 'https://tabun.everypony.ru/blog/news/1.html', False, ['Т2', 'Т3'], False),
    (6, 'news', 'https://tabun.everypony.ru/blog/news/1.html', False, ['Т2, Т3'], True),
    (None, None, 'https://tabun.everypony.ru/blog/1.html', True, ['Т2', 'Т3'], False)
])
def test_add_poll_ok(form_intercept, set_mock, user, blog_id, blog, result_url, draft, tags, forbid_comment):
    set_mock({
        '/question/add/': (None, {
            'headers': {'location': result_url},
            'status': 302, 'status_msg': 'Found'
        }
    )})
    @form_intercept('/question/add/')
    def poll_add(data, headers):
        assert data.get('blog_id') == [text(blog_id if blog_id is not None else 0).encode('utf-8')]
        assert data.get('security_ls_key') == [b'0123456789abcdef0123456789abcdef']
        assert data.get('topic_title') == ['Т0'.encode('utf-8')]
        assert data.get('answer[]') == [b'foo', b'bar']
        assert data.get('topic_text') == ['Б1'.encode('utf-8')]
        assert data.get('topic_tags') == ['Т2, Т3'.encode('utf-8')]
        if draft:
            assert data.get('submit_topic_save') == ['Сохранить в черновиках'.encode('utf-8')]
        else:
            assert data.get('submit_topic_publish') == ['Опубликовать'.encode('utf-8')]
        if forbid_comment:
            assert data.get('topic_forbid_comment') == [b'1']
        else:
            assert 'topic_forbid_comment' not in data

    result = user.add_poll(blog_id, 'Т0', ('foo', 'bar'), 'Б1', tags, forbid_comment, draft=draft)
    assert result == (blog, 1)


def test_add_poll_error(set_mock, user):
    set_mock({'/question/add/': 'topic_add_error.html'})
    with pytest.raises(api.TabunResultError) as excinfo:
        user.add_poll(None, '', ('foo', 'bar'), '', [])
    # TODO: test len(choices) > 20
    assert excinfo.value.message == 'Поле Заголовок слишком короткое (минимально допустимо 2 символов)'


@pytest.mark.parametrize("blog_id,blog,result_url,draft,tags,forbid_comment", [
    (6, 'news', 'https://tabun.everypony.ru/blog/news/1.html', False, ['Т2', 'Т3'], False),
    (6, 'news', 'https://tabun.everypony.ru/blog/news/1.html', False, ['Т2, Т3'], True),
    (None, None, 'https://tabun.everypony.ru/blog/1.html', True, ['Т2', 'Т3'], False)
])
def test_edit_post_ok(form_intercept, set_mock, user, blog_id, blog, result_url, draft, tags, forbid_comment):
    set_mock({
        '/topic/edit/1/': (None, {
            'headers': {'location': result_url},
            'status': 302, 'status_msg': 'Found'
        }
    )})
    @form_intercept('/topic/edit/1/')
    def topic_edit(data, headers):
        assert data.get('blog_id') == [text(blog_id if blog_id is not None else 0).encode('utf-8')]
        assert data.get('security_ls_key') == [b'0123456789abcdef0123456789abcdef']
        assert data.get('topic_title') == ['Т0'.encode('utf-8')]
        assert data.get('topic_text') == ['Б1'.encode('utf-8')]
        assert data.get('topic_tags') == ['Т2, Т3'.encode('utf-8')]
        if draft:
            assert data.get('submit_topic_save') == ['Сохранить в черновиках'.encode('utf-8')]
        else:
            assert data.get('submit_topic_publish') == ['Опубликовать'.encode('utf-8')]
        if forbid_comment:
            assert data.get('topic_forbid_comment') == [b'1']
        else:
            assert 'topic_forbid_comment' not in data

    result = user.edit_post(1, blog_id, 'Т0', 'Б1', tags, forbid_comment, draft=draft)
    assert result == (blog, 1)


def test_edit_post_error(set_mock, user):
    set_mock({'/topic/edit/1/': 'topic_add_error.html'})
    with pytest.raises(api.TabunResultError) as excinfo:
        user.edit_post(1, None, '', '', [])
    assert excinfo.value.message == 'Поле Заголовок слишком короткое (минимально допустимо 2 символов)'


# Тесты hashsum гарантируют обратную совместимость, так что лучше их не трогать


def test_post_hashsum_default(user):
    p = user.get_posts('/')
    oldver_fields = ('post_id', 'time', 'draft', 'author', 'blog', 'title', 'body', 'tags')
    assert p[0].post_id == 100000
    assert p[0].hashsum(oldver_fields) == 'e93efead3145c59b9aac26037b9c5fcf'
    assert p[1].post_id == 131909
    assert p[1].hashsum(oldver_fields) == 'b6147c9ba6dbc7e8e07db958390108bd'
    assert p[2].post_id == 131911
    assert p[2].hashsum(oldver_fields) == '33b7a175c45eea8e5f68f4bc885f324b'
    assert p[3].post_id == 131915
    assert p[3].hashsum(oldver_fields) == '51b480ee57ee3166750e4f15f6a48f1f'
    assert p[4].post_id == 131904
    assert p[4].hashsum(oldver_fields) == 'd28e3ff695cd4cdc1f63e5919da95516'
    assert p[5].post_id == 131937
    assert p[5].hashsum(oldver_fields) == '93ef694d929b03b2f48b702ef68ce77b'

    assert p[0].hashsum() == '2f452e09ee106a2beeb5a48927ad72b3'
    assert p[1].hashsum() == '5308ccc03831ea4f4f3f3661440fcc75'
    assert p[2].hashsum() == 'fb329febe4d073359b1d974098557994'
    assert p[3].hashsum() == 'bed41b4d1ab3fa5b6b340f186067d6d5'
    assert p[4].hashsum() == '2c49d10769e1fb28cb78cfaf8ac6cd0e'
    assert p[5].hashsum() == '6c35ba542fd4f65ab9aac97943ca6672'


def test_post_hashsum_part(user):
    p = user.get_posts('/')
    assert p[0].post_id == 100000
    assert p[0].hashsum(('title', 'body', 'tags')) == 'efeff4792ac7666c280b06d6d0ae1136'
    assert p[1].post_id == 131909
    assert p[1].hashsum(('title', 'body', 'tags')) == 'dacf2a4631636a1ab796681d607c11e0'
    assert p[2].post_id == 131911
    assert p[2].hashsum(('title', 'body', 'tags')) == '1381908ebf93038617b400f59d97646a'
    assert p[3].post_id == 131915
    assert p[3].hashsum(('title', 'body', 'tags')) == '9fbca162a43f2a2b1dff8c5764864fdf'
    assert p[4].post_id == 131904
    assert p[4].hashsum(('title', 'body', 'tags')) == '61a43c4d0f33313bfb4926fb86560450'
    assert p[5].post_id == 131937
    assert p[5].hashsum(('title', 'body', 'tags')) == 'a49976cb3879a540334a3e93f57a752e'

    # Потому что смешивать \n и \r\n в файлах так же, как и на сайте, очень геморройно
    p[0].raw_body = p[0].raw_body.replace('\n', '\r\n')
    assert p[0].hashsum(('title', 'body', 'tags')) == '1364ee5a2fee913325d3b220d43623a5'


# TODO: rss
