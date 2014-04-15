#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import time
import random
import urllib2
import mimetypes
from hashlib import md5
import lxml
import lxml.html
import lxml.etree
#import html5lib

#: Месяцы, для парсинга даты.
mons = (u'января', u'февраля', u'марта', u'апреля', u'мая', u'июня', u'июля', u'августа', u'сентября', u'октября', u'ноября', u'декабря')

def parse_html(data, encoding='utf-8'):
    """Парсит HTML-код и возвращает lxml.etree-элемент."""
    #if isinstance(data, unicode): encoding = None
    #doc = html5lib.parse(data, treebuilder="lxml", namespaceHTMLElements=False, encoding=encoding)
    if isinstance(data, str): data = data.decode(encoding, "replace")
    doc = lxml.html.fromstring(data)
    return doc

def parse_html_fragment(data, encoding='utf-8'):
    """Парсит кусок HTML-кода и возвращает lxml.etree-элемент."""
    #if isinstance(data, unicode): encoding = None
    #doc = html5lib.parseFragment(data, treebuilder="lxml", namespaceHTMLElements=False, encoding=encoding)
    if isinstance(data, str): data = data.decode(encoding, "replace")
    doc = lxml.html.fragments_fromstring(data)
    return doc

block_elems = ("div", "p", "blockquote", "section", "ul", "li", "h1", "h2", "h3", "h4", "h5", "h6")
def htmlToString(node, with_cutted=True, fancy=True, vk_links=False, hr_lines=True):
    """Пытается косплеить браузер lynx и переделывает html-элемент в читабельный текст.
    
    * node: текст поста, html-элемент, распарсенный с помощью parse_html[_fragment]
    * with_cutted: выводить ли содержимое, которое под катом
    * fancy: если True, выкинет заголовки спойлеров и текст кнопки «Читать дальше» (при наличии, разумеется)
    * vk_links: преобразует ссылки вида http://vk.com/blablabla в [blablabla|текст ссылки] для отправки в пост ВКонтакте
    * hr_lines: если True, добавляет линию из знаков равно на месте тега hr, иначе просто перенос строки
    """
    data = u""
    newlines = 0
    
    if node.text:
        ndata = node.text.replace(u"\n", u" ")
        if newlines: ndata = ndata.lstrip()
        data += ndata
        if ndata: newlines = 0
    
    prev_text = None
    prev_after = None
    for item in node.iterchildren():
        if prev_text:
            ndata = prev_text.replace(u"\n", u" ")
            if newlines: ndata = ndata.lstrip()
            data += ndata
            if ndata: newlines = 0
        if prev_after:
            ndata = prev_after.replace(u"\n", u" ")
            if newlines: ndata = ndata.lstrip()
            data += ndata
            if ndata: newlines = 0
        
        if item.tail:
            prev_after = item.tail
        else:
            prev_after = None
        prev_text = item.text
        
        if item.tag == "br":
            if newlines < 2:
                data += u"\n"
                newlines += 1
        elif item.tag == "hr":
            if hr_lines: data += u"\n=====\n"
            else: data += u"\n"
            newlines = 1
        elif fancy and item.get('class') == 'spoiler-title':
            prev_text = None
            continue
        elif fancy and item.tag == 'a' and item.get('title') == u"Читать дальше":
            prev_text = None
            continue
        elif not with_cutted and item.tag == "a" and item.get("rel") == "nofollow" and not item.text_content() and not item.getchildren():
            return data.strip()
        elif item.tag in ("img",):
            continue
        
        elif vk_links and item.tag == "a" and item.get('href', '').find("://vk.com/") > 0 and item.text_content().strip():
            href = item.get('href')
            addr = href[href.find("com/")+4:]
            if addr and addr[-1] in (".", ")"): addr = addr[:-1]
            
            stop=False
            for c in (u"/", u"?", u"&", u"(", u",", u")", u"|"):
                if c in addr:
                    stop=True
                    break
            if stop:
                data += item.text_content()
                prev_text = None
                continue
            
            for typ in (u"wall", u"photo", u"page", u"video", u"topic", u"app"):
                if addr.find(typ) == 0:
                    stop=True
                    break
            if stop:
                data += item.text_content()
                prev_text = None
                continue
            
            ndata = item.text_content().replace("[", " ").replace("|", " ").replace("]", " ")
            data += " [" + addr + "|" + ndata + "] "
            prev_text = None
        
        else:
            if item.tag in ("li", ):
                data += u"• "
            elif data and item.tag in block_elems and not newlines:
                data += u"\n"
                newlines = 1
            
            if prev_text:
                prev_text = None
                
            tmp = htmlToString(item, fancy=fancy, vk_links=vk_links, hr_lines=hr_lines)
            newlines = 0
            
            if item.tag == "s": # зачёркивание
                tmp1=""
                for x in tmp:
                    tmp1 += x + u'\u0336'
                #tmp1 = "<s>" + tmp1 + "</s>"
            elif item.tag == "blockquote": # цитата
                tmp1 = u" «" + tmp + u"»\n"
                newlines = 1
            else: tmp1 = tmp
            
            data += tmp1
            
            if item.tag in block_elems and not newlines:
                data += u"\n"
                newlines = 1
                
    if prev_text:
        ndata = prev_text.replace(u"\n", u" ")
        if newlines: ndata = ndata.lstrip()
        data += ndata
        if ndata: newlines = 0
    if prev_after:
        ndata = prev_after.replace(u"\n", u" ")
        if newlines: ndata = ndata.lstrip()
        data += ndata
        if ndata: newlines = 0

    return data.strip()

def node2string(node):
    """Переводит html-элемент обратно в строку."""
    return lxml.etree.tostring(node, method="html", encoding="utf-8")

def mon2num(s):
    """Переводит названия месяцев в числа, чтобы строку можно было скормить в strftime."""
    for i in range(len(mons)):
        s = s.replace(mons[i], str(i+1))
    return s

def find_images(body, spoiler_title=True, no_other=False):
    """Ищет картинки в lxml-элементе и возвращает их список в виде [[ссылки до ката], [ссылки после ката]].
    spoiler_title (True) - включать ли картинки с заголовков спойлеров
    no_other (False) не включать ли всякий мусор. Фильтрация простейшая: по наличию "smile" или "gif" в ссылке."""
    
    imgs = [[], []]
    links = [[], []]
    
    start = False
    for item in body.iterchildren():
        if not start and item.tag == "a" and item.get("rel") == "nofollow" and not item.text_content() and not item.getchildren():
            start = True
            continue
        
        if item.tag == "img":
            imgs[1 if start else 0].append(item)
        else:
            limgs = item.xpath('.//img')
            if not limgs: limgs = item.xpath('.//a')
            imgs[1 if start else 0].extend(limgs)

    for i in (0,1):
        tags = imgs[i]
        if not tags: continue
        for img in tags:
            src = img.get("src")
            if not src:
                src = img.get("href")
                if not src: continue
                if not src[-4:].lower() not in (u'jpeg', u'.jpg', u'.png'):
                    continue
            if "<" in src: continue
            if no_other and (".gif" in src.lower() or "smile" in src.lower()):
                continue
            
            if not spoiler_title and img.getparent() is not None and img.getparent().get("class") == "spoiler-title":
                # Hint: если вы пишете пост и хотите, чтобы картика бралась даже из заголовка спойлера,
                # достаточно лишь положить её внутрь какого-нибудь ещё тега, например <strong>.
                continue
           
            links[i].append(src)
    
    return links

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

def find_substring(s, start, end, extend=False, with_start=True, with_end=True):
    """Возвращает подстроку, находящуюся между кусками строки start и end, или None, если не нашлось. При extend=True кусок строки end ищется с конца (rfind)."""
    f1 = s.find(start)
    if f1 < 0: return
    f2 = (s.rfind if extend else s.find)(end, f1 + len(start))
    if f2 < 0: return
    return s[f1 + (0 if with_start else len(start)):f2 + (len(end) if with_end else 0)]

def find_good_image(urls, maxmem=20*1024*1024):
    """Ищет годную картинку из предложенного списка ссылок и возвращает ссылку и скачанные данные картинки (файл). Такой простенький фильтр смайликов и элементов оформления поста по размеру. Требует PIL. Не грузит картинки размером больше maxmem байт, дабы не вылететь от нехватки памяти."""
    try:
        import Image
    except ImportError:
        from PIL import Image
    from StringIO import StringIO
    
    good_image = None, None
    for url in urls:
        try:
            req = urllib2.urlopen(url.encode("utf-8") if isinstance(url, unicode) else url, timeout=5)
            size = req.headers.get('content-length')
            if size and size.isdigit() and int(size) > maxmem:
                continue
            data = req.read(maxmem + 1)
        except IOError: continue
        if len(data) > maxmem:
            continue
        
        try: img = Image.open(StringIO(data))
        except: continue
        
        if img.size[0] < 100 or img.size[1] < 100: continue
        good_image = url, data
        break
    
    return good_image
