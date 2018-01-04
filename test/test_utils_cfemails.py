#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import pytest

from tabun_api import utils


test_cases = [(
    'old_link_href_attrs_text',

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
    '''/* ]]> */</script></a>''',

    '<a left="1" href="mailto:почта@ya.ru" right="2">почта@ya.ru</a>',
), (
    'old_link_href_text',

    '''<a href="/cdn-cgi/l/email-protection#ff2f402f412e782e7d2f4fbf869ed18d8a">'''
    '''<div class="__cf_email__" data-cfemail="c818771876194f194a187888b1a9e6babd">[email&#160;protected]</div>'''
    '''<script data-cfhash='f9e31' type="text/javascript">/* <![CDATA[ */!'''
    '''function(t,e,r,n,c,a,p){try{t=document.currentScript||function(){'''
    '''for(t=document.getElementsByTagName('script'),e=t.length;e--;)'''
    '''if(t[e].getAttribute('data-cfhash'))return t[e]}();if(t&&(c=t.previousSibling))'''
    '''{p=t.parentNode;if(a=c.getAttribute('data-cfemail')){'''
    '''for(e='',r='0x'+a.substr(0,2)|0,n=2;a.length-n;n+=2)'''
    '''e+='%'+('0'+('0x'+a.substr(n,2)^r).toString(16)).slice(-2);'''
    '''p.replaceChild(document.createTextNode(decodeURIComponent(e)),c)'''
    '''}p.removeChild(t)}}catch(u){}}()'''
    '''/* ]]> */</script></a>''',

    '<a href="mailto:почта@ya.ru">почта@ya.ru</a>',
), (
    'link_href_attrs',
    '<a title="1" href="/cdn-cgi/l/email-protection#1bcba4cba5ca9cca99cbab5b7e6d7e69626b74756235696e" target="_blank">foo</a><br/>',
    '<a title="1" href="mailto:почта@everypony.ru" target="_blank">foo</a><br/>',
), (
    'link_href_attrs_text',
    '<a title="1" href="/cdn-cgi/l/email-protection#d1016e016f00560053016191b4a7b4a3a8a1bebfa8ffa3a4" target="_blank"><span class="__cf_email__" data-cfemail="d0a0bfb3b8a4b190b5a6b5a2a9a0bfbea9fea2a5">[email&#160;protected]</span></a>',
    '<a title="1" href="mailto:почта@everypony.ru" target="_blank">pochta@everypony.ru</a>',
), (
    'text',
    '<a href="/cdn-cgi/l/email-protection" class="__cf_email__" data-cfemail="572738343f233617322132252e2738392e792522">[email&#160;protected]</a>',
    'pochta@everypony.ru',
)]


@pytest.mark.parametrize(
    'input_html,output_html',
    [pytest.param(*x[1:], id=x[0]) for i, x in enumerate(test_cases)]
)
def test_replace_cloudflare_emails_unicode(input_html, output_html):
    assert utils.replace_cloudflare_emails(input_html.encode('utf-8')) == output_html.encode('utf-8')


@pytest.mark.parametrize(
    'input_html,output_html',
    [pytest.param(*x[1:], id=x[0]) for i, x in enumerate(test_cases)]
)
def test_replace_cloudflare_emails_bytes(input_html, output_html):
    assert utils.replace_cloudflare_emails(input_html.encode('utf-8')) == output_html.encode('utf-8')
