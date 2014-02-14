#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import time
import random
import urllib2
import mimetypes
from hashlib import md5

# copypasted from http://code.activestate.com/recipes/146306-http-client-to-post-using-multipartform-data/
# and modified by andreymal
def encode_multipart_formdata(fields, files):
    """
    Возвращает (content_type, body), готовое для отправки HTTP-запроса
    
    * fields - список из элементов (имя, значение) или словарь полей формы
    * files - список из элементов (имя, имя файла, значение) для данных, загружаемых в виде файлов
    """
    if isinstance(fields, dict): fields = fields.items()
    BOUNDARY = '----------' + md5(str(int(time.time())) + str(random.randrange(1000))).hexdigest()
    L = []
    for (key, value) in fields:
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"' % key)
        L.append('')
        L.append(value)
    for (key, filename, value) in files:
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
        L.append('Content-Type: %s' % get_content_type(filename))
        L.append('')
        L.append(value)
    L.append('--' + BOUNDARY + '--')
    L.append('')
    body = '\r\n'.join(L)
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    return content_type, body
    
def get_content_type(filename):
    """return mimetypes.guess_type(filename)[0] or 'application/octet-stream'"""
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    
def send_form(url, fields, files, timeout=None, headers={}):
    """
    Отправляет форму, пользуясь функцией encode_multipart_formdata(fields, files), возвращает результат вызова urllib2.urlopen
    
    * timeout - сколько ожидать ответа, не дождётся - кидается исключением urllib2
    * headers - дополнительные HTTP-заголовки
    """
    content_type, data = encode_multipart_formdata(fields, files)
    if not isinstance(url, urllib2.Request): url = urllib2.Request(url)
    if isinstance(headers, dict): headers = headers.items()
    if headers:
        for header, value in headers: url.add_header(header, value)
    url.add_header('content-type', content_type)
    if timeout is None:
        return urllib2.urlopen(url, data)
    else:
        return urllib2.urlopen(url, data, timeout)
