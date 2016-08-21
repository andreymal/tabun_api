#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=W0611, W0613, W0621, E1101

from __future__ import unicode_literals

import pytest
import lxml.html
from tabun_api import utils
from tabun_api.compat import PY2, text, binary

from testutil import user


def hf(data, with_cutted=True, **kwargs):
    if isinstance(data, text):
        node = lxml.html.fragments_fromstring(data)[0]
    else:
        node = data
    f = utils.HTMLFormatter(kwargs)
    return f.format(node, with_cutted=with_cutted)


def test_formatter_str():
    assert utils.HTMLFormatter().format('a<br/>bc') == 'a<br/>bc'


def test_formatter_span():
    assert hf('<div>a<span>bc</span>d</div>') == 'abcd'


def test_formatter_spaces_begin():
    assert hf('<div>\n  \t a  \r\t  b \n</div>') == 'a b'


def test_formatter_spaces_middle():
    assert hf('<div><span>\n  \t a  \r\t  b \n</span></div>') == 'a b'


def test_formatter_spaces_end():
    assert hf('<div><span>qwe</span>\n  \t a  \r\t  b \n</div>') == 'qwe a b'


def test_formatter_spaces_br():
    assert hf('<div>\n  \t a  \r\t <br/>  b \n</div>') == 'a\nb'


def test_formatter_spaces_br_two():
    assert hf('<div>\n  \t a  \r\t <br/><br/>  b \n</div>') == 'a\n\nb'


def test_formatter_spaces_br_many():
    assert hf('<div>\n  \t a  \r\t <br/><br/> <br/>  b \n</div>') == 'a\n\nb'


def test_formatter_hr():
    assert hf('<div>\n  \t a  \r\t <hr/>  b \n</div>') == 'a\n=====\nb'


def test_formatter_blockquote():
    assert hf('<div>a<blockquote>bc</blockquote>d</div>') == 'a\n«bc»\nd'


def test_formatter_ul():
    assert hf('<div>0<ul><li>1</li>2<li>3</li>4</ul>5</div>') == '0\n• 1\n2\n• 3\n4\n5'


def test_formatter_s_unicode():
    assert hf('<div>a<s>bc</s>d</div>') == 'ab\u0336c\u0336d'


def test_formatter_s_html():
    assert hf('<div>a<s>bc</s>d</div>', strike_mode='html') == 'a<s>bc</s>d'


def test_formatter_s_unknown():
    assert hf('<div>a<s>bc</s>d</div>', strike_mode='asSDssdvxcv') == 'abcd'


def test_formatter_spoiler_fancy():
    html = '<div>q<span class="spoiler"><span class="spoiler-title">title</span><span class="spoiler-body">body</span></span></div>'
    assert hf(html) == 'q\nbody'


def test_formatter_spoiler_empty():
    html = '<div>q<span class="spoiler"><span class="spoiler-title">title</span><span class="spoiler-body"></span></span>w</div>'
    assert hf(html) == 'q\nw'


def test_formatter_spoiler_nofancy():
    html = '<div>q<span class="spoiler"><span class="spoiler-title">title</span><span class="spoiler-body">body</span></span></div>'
    assert hf(html, fancy=False) == 'qtitlebody'


def test_formatter_spoiler_fake():
    html = '<div>q<span class="spoiler-title">title</span><span class="spoiler-body">body</span>w</div>'
    assert hf(html) == 'qw'


def test_formatter_spoiler_fake_inline():
    html = '<div>q<span class="spoiler"><span class="spoiler-title">title</span><span class="spoiler-body">'
    html += '<span class="spoiler-title">fa</span>!<span class="spoiler-body">ke</span>'
    html += 'body</span></span></div>'
    assert hf(html) == 'q\n!body'


def test_formatter_link_cut():
    assert hf('<div>аб<a title="Читать дальше">Кат там!</a>вг</div>') == 'абвг'


def test_formatter_with_cutted(user):
    post = user.get_post(138982, 'borderline')
    assert hf(post.body) == 'Текст до ката\n\nТекст после ката'


def test_formatter_without_cutted(user):
    post = user.get_post(138982, 'borderline')
    assert hf(post.body, with_cutted=False) == 'Текст до ката'


def test_formatter_without_cutted_including():
    assert hf('<div>abc<blockquote>d<a></a>e</blockquote>f</div>', with_cutted=False) == 'abc\n«d'


def test_formatter_without_cutted_including_recursive():
    assert hf('<div>abc<s>d<a></a>e</s>f</div>', with_cutted=False) == 'abcd\u0336'


def test_formatter_with_cutted_spoiler(user):
    post = user.get_post(138983)
    assert hf(post.body) == 'Перед катом После ката'


def test_formatter_with_cutted_with_spoiler_title(user):
    post = user.get_post(138983)
    assert hf(post.body, fancy=False) == 'Кат внутри спойлераПеред катом После ката'


def test_formatter_without_cutted_spoiler(user):
    post = user.get_post(138983)
    assert hf(post.body, with_cutted=False) == 'Перед катом'


def test_formatter_escape_novk():
    assert hf('<div>@andreymal (andreymal) *</div>') == '@andreymal (andreymal) *'


def test_formatter_escape_withvk():
    assert hf('<div>@andreymal (andreymal) *</div>', vk_links=True) == '&#64;andreymal &#40;andreymal&#41; &#42;'


def test_formatter_vklinks_disabled():
    html = '<div>«<a href="https://new.vk.com/andreymal">andre@(ym)al</a>»</div>'
    assert hf(html) == '«andre@(ym)al»'


def test_formatter_vklinks_enabled_ok():
    html = '<div>«<a href="https://new.vk.com/andreymal">andre@(ym)al</a>»</div>'
    assert hf(html, vk_links=True) == '« @andreymal (andre&#64;&#40;ym&#41;al) »'


def test_formatter_vklinks_enabled_empty():
    html = '<div>«<a href="https://new.vk.com/andreymal"><img src="https://andreymal.org/files/ava.png" alt="" /></a>»</div>'
    assert hf(html, vk_links=True) == '«»'


def test_formatter_vklinks_enabled_invalid1():
    html = '<div>«<a href="https://new.vk.com/wall1">andre@(ym)al</a>»</div>'
    assert hf(html, vk_links=True) == '«andre&#64;&#40;ym&#41;al»'


def test_formatter_vklinks_enabled_invalid2():
    html = '<div>«<a href="https://new.vk.com/album-40_376">andre@(ym)al</a>»</div>'
    assert hf(html, vk_links=True) == '«andre&#64;&#40;ym&#41;al»'


def test_formatter_vklinks_enabled_invalid3():
    html = '<div>«<a href="https://new.vk.com/videos1?section=album_3">andre@(ym)al</a>»</div>'
    assert hf(html, vk_links=True) == '«andre&#64;&#40;ym&#41;al»'


def test_formatter_vklinks_enabled_invalid_fake():
    html = '<div>«<a href="https://new.vk.com/wallie">andre@(ym)al</a>»</div>'
    assert hf(html, vk_links=True) == '« @wallie (andre&#64;&#40;ym&#41;al) »'


def test_formatter_links_nodisable():
    assert hf('<div>a<a href="http://ya.ru/">ya.ru/</a>b</div>') == 'aya.ru/b'


def test_formatter_links_disable_ok1():
    assert hf('<div>a<a href="http://ya.ru/">ya.ru/</a>b</div>', disable_links=True) == 'ab'


def test_formatter_links_disable_ok2():
    assert hf('<div>a<a href="//ya.ru/">ya.ru/</a>b</div>', disable_links=True) == 'ab'


def test_formatter_links_disable_fake1():
    assert hf('<div>a<a href="//ya.ru/">ya.ru</a>b</div>', disable_links=True) == 'aya.rub'


def test_formatter_links_disable_fake2():
    assert hf('<div>a<a href="//google.ru/">rambler.ru</a>b</div>', disable_links=True) == 'arambler.rub'


def test_find_images_cutted(user):
    post = user.get_post(138982, 'borderline')
    assert utils.find_images(post.body) == [['https://i.imgur.com/V3KzzyAs.png'], ['https://i.imgur.com/NAg929K.jpg']]


def test_parse_datetime_2015():
    assert utils.parse_datetime('2015-01-01T02:00:00+03:00').strftime('%Y-%m-%d %H:%M:%S') == '2014-12-31 23:00:00'


def test_parse_datetime_2015_noutc():
    assert utils.parse_datetime('2015-01-01T02:00:00+03:00', utc=False).strftime('%Y-%m-%d %H:%M:%S') == '2015-01-01 02:00:00'


def test_parse_datetime_2015_utc():
    assert utils.parse_datetime('2015-01-01T02:00:00Z').strftime('%Y-%m-%d %H:%M:%S') == '2015-01-01 02:00:00'


def test_parse_datetime_2014_04():
    assert utils.parse_datetime('2014-10-26T01:59:59+04:00').strftime('%Y-%m-%d %H:%M:%S') == '2014-10-25 21:59:59'


def test_parse_datetime_2014_03():
    assert utils.parse_datetime('2014-10-26T01:00:00+03:00').strftime('%Y-%m-%d %H:%M:%S') == '2014-10-25 22:00:00'


def test_replace_cloudflare_emails():
    data = (
        '''<a left="1" href="/cdn-cgi/l/email-protection#ff2f402f412e782e7d2f4fbf869ed18d8a" right="2">'''
        '''<span class="__cf_email__" data-cfemail="c818771876194f194a187888b1a9e6babd">[email&#160;protected]</span>'''
        '''<script data-cfhash='f9e31' type="text/javascript">/* <![CDATA[ */!'''
        '''function(t,e,r,n,c,a,p){try{t=document.currentScript||function(){'''
        '''for(t=document.getElementsByTagName('script'),e=t.length;e--;)'''
        '''if(t[e].getAttribute('data-cfhash'))return t[e]}();if(t&&(c=t.previousSibling))'''
        '''{p=t.parentNode;if(a=c.getAttribute('data-cfemail')){'''
        '''for(e='',r='0x'+a.substr(0,2)|0,n=2;a.length-n;n+=2)'''
        '''e+='%'+('0'+('0x'+a.substr(n,2)^r).toString(16)).slice(-2);'''
        '''p.replaceChild(document.createTextNode(decodeURIComponent(e)),c)'''
        '''}p.removeChild(t)}}catch(u){}}()'''
        '''/* ]]> */</script></a>'''
    )

    result = '<a left="1" href="mailto:почта@ya.ru" right="2">почта@ya.ru</a>'

    assert utils.replace_cloudflare_emails(data) == result
    assert utils.replace_cloudflare_emails(data.encode('utf-8')) == result.encode('utf-8')


def test_html_escape_nosingle_str():
    assert utils.html_escape('&lt;"<>\'') == '&amp;lt;&quot;&lt;&gt;\''


def test_html_escape_nosingle_bytes():
    assert utils.html_escape(b'&lt;"<>\'') == b'&amp;lt;&quot;&lt;&gt;\''


def test_html_escape_single_str():
    assert utils.html_escape('&lt;"<>\'', True) == '&amp;lt;&quot;&lt;&gt;&#39;'


def test_html_escape_single_bytes():
    assert utils.html_escape(b'&lt;"<>\'', True) == b'&amp;lt;&quot;&lt;&gt;&#39;'


def test_get_cookies_dict():
    from io import BytesIO
    if PY2:
        from httplib import HTTPMessage
    else:
        from http.client import parse_headers

    fp = BytesIO(
        b'Set-Cookie: a=b; path=/\r\n'
        b'Set-Cookie: c=d; path=/\r\n'
        b'\r\n'
    )

    if PY2:
        msg = HTTPMessage(fp)
    else:
        msg = parse_headers(fp)

    cookies = utils.get_cookies_dict(msg)
    assert cookies == {'a': 'b', 'c': 'd'}
    for k, v in cookies.items():
        assert isinstance(k, text)
        assert isinstance(v, text)
