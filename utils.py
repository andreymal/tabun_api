#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import re
import time
import random
import urllib2
import mimetypes
from hashlib import md5
import lxml
import lxml.html
import lxml.etree
# import html5lib

#: Месяцы, для парсинга даты.
mons = (u'января', u'февраля', u'марта', u'апреля', u'мая', u'июня', u'июля', u'августа', u'сентября', u'октября', u'ноября', u'декабря')

#: Блочные элементы, для красивого вывода в htmlToString.
block_elems = ("div", "p", "blockquote", "section", "ul", "li", "h1", "h2", "h3", "h4", "h5", "h6")

#: Регулярка для парсинга ютуба для выдирания превьюшки.
youtube_regex = re.compile(r'youtube.com\/embed\/(.{10,15})((\?)|($))')

#: Регулярка для парсинга ссылки на аватарку — из неё можно узнать много полезного!
ava_regex = re.compile(r"\/images\/([0-9]+)\/([0-9]+)\/([0-9]+)\/([0-9]+)\/([0-9]+)\/([0-9]+)\/avatar_([0-9]+)x([0-9]+)\.(...)(\?([0-9]+))?")


def parse_html(data, encoding='utf-8'):
    """Парсит HTML-код и возвращает lxml.etree-элемент."""
    # if isinstance(data, unicode): encoding = None
    # doc = html5lib.parse(data, treebuilder="lxml", namespaceHTMLElements=False, encoding=encoding)
    if isinstance(data, str):
        data = data.decode(encoding, "replace")
    doc = lxml.html.fromstring(data)
    return doc


def parse_html_fragment(data, encoding='utf-8'):
    """Парсит кусок HTML-кода и возвращает список lxml.etree-элементов и строк."""
    # if isinstance(data, unicode): encoding = None
    # doc = html5lib.parseFragment(data, treebuilder="lxml", namespaceHTMLElements=False, encoding=encoding)
    if isinstance(data, str):
        data = data.decode(encoding, "replace")
    doc = lxml.html.fragments_fromstring(data)
    return doc


def htmlToString(node, with_cutted=True, fancy=True, vk_links=False, hr_lines=True, disable_links=False):
    """Пытается косплеить браузер lynx и переделывает html-элемент в читабельный текст.

    * node: текст поста, html-элемент, распарсенный с помощью parse_html[_fragment]
    * with_cutted: выводить ли содержимое, которое под катом
    * fancy: если True, выкинет заголовки спойлеров и текст кнопки «Читать дальше» (при наличии, разумеется)
    * vk_links: преобразует ссылки вида http://vk.com/blablabla в [blablabla|текст ссылки] для отправки в пост ВКонтакте
    * hr_lines: если True, добавляет линию из знаков равно на месте тега hr, иначе просто перенос строки
    * disable_links: если True, то будут проигнорированы ссылки, текст которых совпадает с самой ссылкой
    """

    if isinstance(node, basestring):
        return unicode(node)

    data = u""
    newlines = 0

    if node.text:
        ndata = node.text.replace(u"\n", u" ")
        if newlines:
            ndata = ndata.lstrip()
        data += ndata
        if ndata:
            newlines = 0

    prev_text = None
    prev_after = None
    for item in node.iterchildren():
        if prev_text:
            ndata = prev_text.replace(u"\n", u" ")
            if newlines:
                ndata = ndata.lstrip()
            data += ndata
            if ndata:
                newlines = 0
        if prev_after:
            ndata = prev_after.replace(u"\n", u" ")
            if newlines:
                ndata = ndata.lstrip()
            data += ndata
            if ndata:
                newlines = 0

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
            if hr_lines:
                data += u"\n=====\n"
            else:
                data += u"\n"
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
            addr = href[href.find("com/") + 4:]
            if addr and addr[-1] in (".", ")"):
                addr = addr[:-1]

            stop = False
            for c in (u"/", u"?", u"&", u"(", u",", u")", u"|"):
                if c in addr:
                    stop = True
                    break
            if stop:
                data += item.text_content()
                prev_text = None
                continue

            for typ in (u"wall", u"photo", u"page", u"video", u"topic", u"app", u"album"):
                if addr.find(typ) == 0:
                    stop = True
                    break
            if stop:
                data += item.text_content()
                prev_text = None
                continue

            ndata = item.text_content().replace("[", " ").replace("|", " ").replace("]", " ")
            data += " [" + addr + "|" + ndata + "] "
            prev_text = None

        elif disable_links and item.tag == "a" and item.get('href', '').endswith(item.text_content().strip()) and abs(len(item.get('href', '')) - len(item.text_content().strip())) < 10:
            prev_text = None
            continue

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

            if item.tag == "s":  # зачёркивание
                tmp1 = ""
                for x in tmp:
                    tmp1 += x + u'\u0336'
                # tmp1 = "<s>" + tmp1 + "</s>"
            elif item.tag == "blockquote":  # цитата
                tmp1 = u" «" + tmp + u"»\n"
                newlines = 1
            else:
                tmp1 = tmp

            data += tmp1

            if item.tag in block_elems and not newlines:
                data += u"\n"
                newlines = 1

    if prev_text:
        ndata = prev_text.replace(u"\n", u" ")
        if newlines:
            ndata = ndata.lstrip()
        data += ndata
        if ndata:
            newlines = 0
    if prev_after:
        ndata = prev_after.replace(u"\n", u" ")
        if newlines:
            ndata = ndata.lstrip()
        data += ndata
        if ndata:
            newlines = 0

    return data.strip()


def node2string(node):
    """Переводит html-элемент обратно в строку."""
    return lxml.etree.tostring(node, method="html", encoding="utf-8")


def mon2num(s):
    """Переводит названия месяцев в числа, чтобы строку можно было скормить в strftime."""
    for i in range(len(mons)):
        s = s.replace(mons[i], str(i + 1))
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
            if not limgs:
                limgs = item.xpath('.//a')
            imgs[1 if start else 0].extend(limgs)

    for i in (0, 1):
        tags = imgs[i]
        if not tags:
            continue
        for img in tags:
            src = img.get("src")
            if not src:
                src = img.get("href")
                if not src:
                    continue
                if src[-4:].lower() not in (u'jpeg', u'.jpg', u'.png'):
                    continue
            if "<" in src:
                continue
            if no_other and (".gif" in src.lower() or "smile" in src.lower()):
                continue

            if not spoiler_title and img.getparent() is not None and img.getparent().get("class") == "spoiler-title":
                # Hint: если вы пишете пост и хотите, чтобы картика бралась даже из заголовка спойлера,
                # достаточно лишь положить её внутрь какого-нибудь ещё тега, например <strong>.
                continue

            links[i].append(src)

    if not links[0] and not links[1]:
        videos = body.xpath('.//iframe')
        for video in videos:
            match = youtube_regex.search(video.get('src', ''))
            if not match:
                continue
            if match.groups()[0]:
                links[1].append('http://i4.ytimg.com/vi/%s/sddefault.jpg' % match.groups()[0])

    return links


# copypasted from http://code.activestate.com/recipes/146306-http-client-to-post-using-multipartform-data/
# and modified by andreymal
def encode_multipart_formdata(fields, files):
    """
    Возвращает (content_type, body), готовое для отправки HTTP-запроса

    * fields - список из элементов (имя, значение) или словарь полей формы
    * files - список из элементов (имя, имя файла, значение) для данных, загружаемых в виде файлов
    """
    if isinstance(fields, dict):
        fields = fields.items()
    BOUNDARY = '----------' + md5(str(int(time.time())) + str(random.randrange(1000))).hexdigest()
    L = []
    for (key, value) in fields:
        key = key.encode("utf-8") if isinstance(key, unicode) else str(key)
        value = value.encode("utf-8") if isinstance(value, unicode) else str(value)
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"' % key)
        L.append('')
        L.append(value)
    for (key, filename, value) in files:
        key = key.encode("utf-8") if isinstance(key, unicode) else str(key)
        filename = filename.encode("utf-8") if isinstance(filename, unicode) else str(filename)
        value = value.encode("utf-8") if isinstance(value, unicode) else str(value)
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


def send_form(url, fields, files, timeout=None, headers=None):
    """
    Отправляет форму, пользуясь функцией encode_multipart_formdata(fields, files), возвращает результат вызова urllib2.urlopen

    * timeout - сколько ожидать ответа, не дождётся - кидается исключением urllib2
    * headers - дополнительные HTTP-заголовки
    """
    content_type, data = encode_multipart_formdata(fields, files)
    if not isinstance(url, urllib2.Request):
        url = urllib2.Request(url)
    if isinstance(headers, dict):
        headers = headers.items()
    if headers:
        for header, value in headers:
            url.add_header(header, value)
    url.add_header('content-type', content_type)
    if timeout is None:
        return urllib2.urlopen(url, data)
    else:
        return urllib2.urlopen(url, data, timeout)


def find_substring(s, start, end, extend=False, with_start=True, with_end=True):
    """Возвращает подстроку, находящуюся между кусками строки start и end, или None, если не нашлось. При extend=True кусок строки end ищется с конца (rfind)."""
    f1 = s.find(start)
    if f1 < 0:
        return
    f2 = (s.rfind if extend else s.find)(end, f1 + len(start))
    if f2 < 0:
        return
    return s[f1 + (0 if with_start else len(start)):f2 + (len(end) if with_end else 0)]


def download(url, maxmem=20 * 1024 * 1024, timeout=5, waitout=15):
    """Скачивает данные по урлу. Имеет защиту от переполнения памяти и слишком долгого ожидания, чтобы всякие боты тут не висли. В случае чего кидает IOError."""
    if url.startswith('//'):
        url = 'http:' + url
    req = urllib2.urlopen(url.encode("utf-8") if isinstance(url, unicode) else url, timeout=timeout)

    size = req.headers.get('content-length')
    if size and size.isdigit() and int(size) > maxmem:
        raise IOError("Too big")

    data = ''
    start_dwnl = time.time()

    while 1:
        if len(data) > maxmem:
            raise IOError("Too big")
        tmp = req.read(128 * 1024)
        if not tmp:
            break
        data += tmp
        if time.time() - start_dwnl >= waitout:
            raise IOError("Too long")
    req.close()

    return data


def find_good_image(urls, maxmem=20 * 1024 * 1024):
    """Ищет годную картинку из предложенного списка ссылок и возвращает ссылку и скачанные данные картинки (файл). Такой простенький фильтр смайликов и элементов оформления поста по размеру. Требует PIL. Не грузит картинки размером больше maxmem байт, дабы не вылететь от нехватки памяти."""
    try:
        import Image
    except ImportError:
        from PIL import Image
    from StringIO import StringIO

    good_image = None, None
    for url in urls:
        try:
            data = download(url, maxmem)
        except IOError:
            continue

        try:
            img = Image.open(StringIO(data))
        except:
            continue

        if img.size[0] < 100 or img.size[1] < 100:
            continue
        good_image = url, data
        break

    return good_image


def generate_comments_tree(comms):
    """Строит дерево комментариев из словаря, возвращаемого функциями get_comments[_from]. Формат элемента: [(комментарий, элемент), (комментарий, элемент), ...] Возвращает само такое дерево и список номеров комментариев-сирот (по идее должен быть пустой, но мало ли)."""
    tree_dict = {}
    tree = []
    orphans = []
    for comment in sorted(comms.values(), key=lambda x: x.comment_id):
        item = (comment, [])
        tree_dict[comment.comment_id] = item
        if not comment.parent_id:
            tree.append(item)
            continue
        parent = tree_dict.get(comment.parent_id)
        if not parent:
            tree.append(item)
            orphans.append(comment.comment_id)
        else:
            parent[1].append(item)
    return tree, orphans


def parse_avatar_url(url):
    """Парсит ссылку на аватарку и возвращает id пользователя, дату отправки, размер, расширение и какой-то номер с конца ссылки."""
    match = ava_regex.search(url)
    if not match:
        return None, None, None, None, None
    g = match.groups()
    user_id = int(g[0] + g[1] + g[2])
    date = g[3] + "-" + g[4] + "-" + g[5]
    size = (int(g[6]), int(g[7]))
    ext = g[8]
    num = int(g[10]) if g[10] is not None else None

    return user_id, date, size, ext, num


def normalize_body(body=None, raw_body=None, cls='text'):
    """Кодирует lxml-элемент в исходник html или наоборот декодирует исходник в lxml-элемент."""
    if body is not None and raw_body is None:
        raw_body = lxml.etree.tostring(body, method="xml", encoding="utf-8").replace('&#13;', '\r').decode('utf-8')
        raw_body = raw_body[raw_body.find(">") + 1:raw_body.rfind("</")]  # <div class="text">body</div>

        # Занимаемся подгонкой под оригинальный исходник
        # Табун принудительно сводит несколько br подряд в <br/>\r\n<br/>, чем и пользуемся, обходя баг lxml
        while '<br/><' in raw_body:
            raw_body = raw_body.replace('<br/><', '<br/>\r\n<')

        raw_body = raw_body.replace(' allowfullscreen=""/>', ' allowfullscreen></iframe>')
        # это типа тег <cut>
        raw_body = raw_body.replace('<a rel="nofollow"/>', '<a rel="nofollow"></a>', 1)
        # однако полученный исходник всё равно не совпадает в точности с исходником на Табуне,
        # например, из-за разного порядка атрибутов, &quot; и битой вёрстки, так что осторожно

    elif raw_body is not None and body is None:
        body = parse_html_fragment(('<div class="%s">' % cls) + raw_body + '</div>')[0]

    return body, unicode(raw_body) if raw_body is not None else None


def escape_topic_contents(data, may_be_short=False):
    """Экранирует содержимое постов для защиты от поехавшей вёрстки и багов lxml."""
    f1 = 0
    f2 = 0
    last_end = 0
    buf = []
    while True:
        # определяем границы тела очередного поста
        f1 = data.find('<div class="topic-content text">', last_end)
        if f1 < 0:
            break
        f2 = data.find('<footer', f1)
        if f2 < 0:
            break
        f2 = data.rfind('</div>', f1, f2)
        if f2 < 0:
            break

        # старые топики-ссылки
        if data.rfind('<div class="topic-url"', f1, f2) > 0:
            f2 = data.rfind('</div>', f1, data.rfind('<div class="topic-url"', f1, f2))
            if f2 < 0:
                break

        # топики-файлы
        if data.rfind('<div class="download"', f1, f2) > 0:
            f2 = data.rfind('</div>', f1, data.rfind('<div class="download"', f1, f2))
            if f2 < 0:
                break

        # выясняем, есть кат или нет
        body = data[data.find('>', f1) + 1:f2].strip()
        short = None
        if may_be_short:
            fa = body.rfind('title="Читать дальше">')
            if fa > 0:
                fa2 = body.find('</a>', fa)
                if fa2 > 0 and fa2 == len(body) - 4:
                    short = body[body.find(">", fa) + 1:fa2].strip()
                    body = body[:body.rfind('<', 0, fa)].rstrip()

        # выпиливаем header при его наличии
        if body.startswith('<header'):
            body = body[body.find('</header>') + 9:].lstrip()

        # экранируем тело
        body = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

        # собираем страницу обратно
        buf.extend((
            data[last_end:f1],
            '<div class="topic-content text" data-escaped="1" data-short="%s" data-short-text="%s">' % (1 if short is not None else 0, short if short is not None else ''),
            body,
            '</div>'
        ))
        last_end = f2 + 6

    buf.append(data[last_end:])
    return ''.join(buf)


def escape_comment_contents(data):
    """Экранирует содержимое комментов."""
    f1 = 0
    f2 = 0
    last_end = 0
    buf = []
    while True:
        # определяем границы очередного коммента
        f1 = data.find('class="comment-content">', last_end)
        if f1 >= 0:
            f = data.find('<div class=" text">', f1, f1 + 150)
            if f < 0:
                f1 = data.find('<div class="text">', f1, f1 + 150)
            else:
                f1 = f
            del f
        if f1 < 0:
            break
        f2 = data.find('<div id="info_edit_', f1)
        if f2 < 0:
            f2 = data.find('<div class="comment-path', f1)
        if f2 < 0:
            break
        f2 = data.rfind('</div>', f1, f2)
        if f2 >= 0:
            f2 = data.rfind('</div>', f1, f2)
        if f2 < 0:
            break

        # экранируем тело
        body = data[data.find('>', f1) + 1:f2].strip()
        body = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

        # собираем страницу обратно
        buf.extend((
            data[last_end:f1],
            '<div class="text" data-escaped="1">',
            body,
            '</div>'
        ))
        last_end = f2 + 6

    buf.append(data[last_end:])
    return ''.join(buf)
