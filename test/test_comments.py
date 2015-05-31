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

from testutil import UserTest, load_file, form_intercept, set_mock, user


@pytest.mark.parametrize("url,data_file,rev", [
    ('/blog/132085.html', '132085_comments.json', False),
    (None, 'comments.json', True)
])
def test_get_comments(user, url, data_file, rev):
    comments_data = json.loads(load_file(data_file, template=False).decode('utf-8'))
    if url:
        comments = user.get_comments(url)
    else:
        comments = user.get_comments()

    assert list(sorted(comments.keys(), reverse=rev)) == [x['comment_id'] for x in comments_data]

    for data in comments_data:
        comment = comments[data['comment_id']]
        assert data['comment_id'] == comment.comment_id

        for key, value in data.items():
            if key == 'time' and value is not None:
                assert time.strftime("%Y-%m-%d %H:%M:%S", comment.time) == value
            elif key != "comment_id":
                assert getattr(comment, key) == value


def test_get_comments_types_ok(user):
    comments = user.get_comments()
    comments.update(user.get_comments('/blog/132085.html'))
    for comment_id, comment in comments.items():
        assert isinstance(comment_id, int)
        assert comment.blog is None or isinstance(comment.blog, text)
        if comment.deleted:
            assert comment.author is None
            assert comment.raw_body is None
            assert comment.vote is None
        else:
            assert isinstance(comment.author, text)
            assert isinstance(comment.raw_body, text)
            assert isinstance(comment.vote, int)


def test_add_comment_ok(form_intercept, set_mock, user):
    set_mock({'/blog/ajaxaddcomment/': (None, {'data': b'{"sCommentId": 1, "sMsgTitle": "", "sMsg": "", "bStateError": false}'})})
    @form_intercept('/blog/ajaxaddcomment/')
    def add_comment(data, headers):
        assert headers.get('content-type', '').startswith('multipart/form-data; boundary=-')

        assert data.get('security_ls_key') == [b'0123456789abcdef0123456789abcdef']
        assert data.get('cmt_target_id') in ([b'1'], [b'2'])
        assert data.get('comment_text') == ['тест'.encode('utf-8')]
        assert data.get('reply') == ([b'0'] if data['cmt_target_id'][0] == b'1' else [b'1'])

    assert user.comment(1, 'тест') == 1
    assert user.comment(1, 'тест', reply=0) == 1

def test_add_comment_fail(set_mock, user):
    err = "Текст комментария должен быть от 2 до 3000 символов и не содержать разного рода каку"
    set_mock({'/blog/ajaxaddcomment/': (None, {'data': ('{"sMsgTitle": "Ошибка", "sMsg": "%s", "bStateError": true}' % err).encode('utf-8')})})
    with pytest.raises(api.TabunResultError) as excinfo:
        user.comment(1, '')
    assert excinfo.value.message == err
