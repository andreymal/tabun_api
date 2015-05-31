#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=all

import sys

PY2 = sys.version_info.major == 2

if PY2:
    import urllib2 as urequest
    from httplib import HTTPException
    from Cookie import BaseCookie
else:
    import urllib.request as urequest
    from http.cookies import BaseCookie
    from http.client import HTTPException

if PY2:
    text_types = (basestring,)
    text = unicode
    binary = str
else:
    text_types = (str,)
    text = str
    binary = bytes
