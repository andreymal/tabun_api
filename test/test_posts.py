#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import time
import json

from testutil import UserTest, load_file, set_mock, user


post_data = json.loads(load_file('index_posts.json', template=False).decode('utf-8'))


def tests_posts_list_ok(user):
    posts = reversed(user.get_posts('/'))
    for data, post in zip(post_data, posts):
        assert post.post_id == data['post_id']
        for key, value in data.items():
            if key == 'time':
                assert time.strftime("%Y-%m-%d %H:%M:%S", post.time) ==  value
            elif key != "post_id":
                assert getattr(post, key) == value
