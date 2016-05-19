#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import re
import sys
import time
import random
import platform
import mimetypes
from hashlib import md5

import lxml
import lxml.html
import lxml.etree
# import html5lib
import iso8601

from .compat import text, text_types, binary, urequest, PY2

#: Месяцы, для парсинга даты.
mons = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')

#: Блочные элементы, для красивого вывода в htmlToString (устарело, используйте HTMLFormatter.block_elems)
block_elems = ("div", "p", "blockquote", "section", "ul", "li", "h1", "h2", "h3", "h4", "h5", "h6")

#: Регулярка для парсинга ютуба для выдирания превьюшки.
youtube_regex = re.compile(r'youtube.com\/embed\/(.{10,15})((\?)|($))')

#: Регулярка для парсинга ссылки на аватарку — из неё можно узнать много полезного!
ava_regex = re.compile(r"\/((images)|(storage))\/([0-9]+)\/([0-9]+)\/([0-9]+)\/([0-9]+)\/([0-9]+)\/([0-9]+)\/avatar_([0-9]+)x([0-9]+)\.(...)(\?([0-9]+))?")

#: Регулярка для расшифровки почты, которую шифрует CloudFlare.
cf_email = re.compile(r'<[A-z]+ class="__cf_email__".*? data-cfemail="([0-9a-f]+)".+?</script>', re.DOTALL)

cf_email_b = re.compile(r'<[A-z]+ class="__cf_email__".*? data-cfemail="([0-9a-f]+)".+?</script>'.encode('utf-8'), re.DOTALL)


def parse_html(data, encoding='utf-8'):
    """Парсит HTML-код и возвращает lxml.etree-элемент."""
    # if isinstance(data, text): encoding = None
    # doc = html5lib.parse(data, treebuilder="lxml", namespaceHTMLElements=False, encoding=encoding)
    if isinstance(data, binary):
        data = data.decode(encoding, "replace")
    doc = lxml.html.fromstring(data)
    return doc


def parse_html_fragment(data, encoding='utf-8'):
    """Парсит кусок HTML-кода и возвращает список lxml.etree-элементов и строк."""
    # if isinstance(data, text): encoding = None
    # doc = html5lib.parseFragment(data, treebuilder="lxml", namespaceHTMLElements=False, encoding=encoding)
    if isinstance(data, binary):
        data = data.decode(encoding, "replace")
    doc = lxml.html.fragments_fromstring(data)
    return doc


class HTMLFormatter(object):
    """Гибкий и расширяемый конвертер lxml-элементов в красивые строки
    подобно браузеру links и родственным ему.

    В словаре ``params`` можно указать следующие параметры:

    * ``fancy`` (True/False, по умолчанию True) — грамотно форматирует спойлеры
      и убирает кнопку ката при наличии
    * ``strike_mode`` (``unicode`` (по умолчанию) или ``html``) — как форматировать
      зачёркивания
    * ``vk_links`` (True/False, по умолчанию False) — преобразует ссылки вида
      ``https://vk.com/foo`` в ``@foo (текст ссылки)`` для отправки во ВКонтакте
    * ``disable_links`` (True/False, по умолчанию False) — удаляет ссылки, если
      текст ссылки совпадает с самой ссылкой (примитивный антиспам)

    Пример использования::

        node = parse_html_fragment('<div>a <s>bc</s> <hr/> d   ef<br/>g<a></a>cut</div>')[0]
        HTMLFormatter({'strike_mode': 'html'}).format(node, with_cutted=False)

    Результат::

        a <s>bc</s>
        =====
        d ef
        g
    """

    NEWLINE = -1
    block_elems = ("div", "p", "blockquote", "section", "ul", "li", "h1", "h2", "h3", "h4", "h5", "h6")

    fancy = True
    strike_mode = 'unicode'
    vk_links = False
    disable_links = False

    def __init__(self, params=None):
        for k in ('fancy', 'strike_mode', 'vk_links', 'disable_links'):
            if params and k in params:
                setattr(self, k, params[k])

    def format(self, node, with_cutted=True):
        """Форматирует lxml-элемент.

        :param node: сам lxml-элемент
        :param bool with_cutted: если False, обработка будет прекращена после
          натыкания на тег-кат (когда :func:`~tabun_api.utils.is_cut` вернёт True)
        :rtype: строка
        """

        return self.format_part(node, with_cutted)[1]

    def format_part(self, node, with_cutted=True):
        if isinstance(node, text_types):
            return False, text(node)

        if node.text:
            data = [self.format_text(self.escape(node.text), [])]
        else:
            data = ['']

        depth = [node]  # for <div><ul><li>: [<div>, <ul>]
        full_queue = [list(node.getchildren())]  # for <div><ul><li>: [[div children after current ul], [ul children after current li]]
        full_queue[0].reverse()

        # Самые часто используемые функции вытащим заранее (говорят, так слегка быстрее)
        process_br = getattr(self, 'process_br', None)
        process_a = getattr(self, 'process_a', None)
        process_span = getattr(self, 'process_span', None)
        default_process = self.default_process
        format_item_tail = self.format_item_tail

        cut_stop = False

        while True:
            # Проверяем, что очередь не пуста
            while full_queue and not full_queue[-1]:
                full_queue.pop()
                depth.pop()
            if not full_queue or not depth:
                assert not depth
                assert not full_queue
                break

            # Берём следующий элемент (может быть любой вложенности — избегаем рекурсии зазря)
            item = full_queue[-1].pop()

            # С помощью специального значения избегаем лишних переносов на границах блоков
            if item == self.NEWLINE:
                sdata = data[-1].rstrip(' ')
                if not sdata.endswith('\n'):
                    data[-1] = sdata
                    data.append('\n')
                continue

            # Это может быть просто текст между элементами (добавляется ниже в format_item_tail)
            if isinstance(item, text_types):
                ntext = self.format_text(item, data)
                if ntext:
                    data.append(ntext)
                continue

            # Это может быть кат в полном посте — тогда сразу закругляемся
            if not with_cutted and is_cut(item):
                cut_stop = True
                break

            format_item_tail(item, data, depth, full_queue)

            children = []

            # Обрабатываем элемент
            tag = item.tag.lower().replace('-', '_')
            if tag == 'br':
                process_func = process_br
            elif tag == 'a':
                process_func = process_a
            elif tag == 'span':
                process_func = process_span
            else:
                process_func = getattr(self, 'process_' + tag, None)

            if process_func is None:
                process_func = default_process
            children = process_func(item, data, depth, with_cutted=with_cutted)

            if children is None:
                # None означает, что надо закругляться
                break

            elif children:
                # Обрабатываем потомков в следующей итерации
                children.reverse()
                full_queue.append(children)
                depth.append(item)

        return cut_stop, ''.join(data).strip()

    def element_children(self, item, noblock=False):
        children = []
        is_block = not noblock and item.tag in self.block_elems

        # Начало элемента-блока
        if is_block:
            children.append(self.NEWLINE)

        # Содержимое элемента
        if item.text:
            children.append(self.escape(item.text))

        ch = list(item.getchildren())
        if ch:
            children.extend(ch)

        # Конец элемента-блока (есть смысл только при непустом блоке)
        if is_block and (item.text or ch):
            children.append(self.NEWLINE)

        return children

    def process_br(self, item, data, depth, with_cutted):
        # Не более одной пустой строчки при нескольких <br/> подряд
        if data[-1].rstrip(' ').endswith('\n\n'):
            pass
        elif len(data) > 1 and data[-1].rstrip(' ') == '\n' and data[-2].rstrip(' ').endswith('\n'):
            pass
        else:
            data[-1] = data[-1].rstrip(' ')
            data.append('\n')
        return []

    def default_process(self, item, data, depth, with_cutted):
        return self.element_children(item)

    def format_item_tail(self, item, data, depth, full_queue):
        # Текст после тега не относится к самому тегу и добавится после обработки потомков
        if item.tail:
            full_queue[-1].append(self.escape(item.tail))

    def format_text(self, ntext, data=None):
        # Форматирует текст подобно HTML — не более одного пробела подряд
        if '\n' in ntext:
            ntext = ntext.replace('\n', ' ')
        if '\r' in ntext:
            ntext = ntext.replace('\r', ' ')
        if '\t' in ntext:
            ntext = ntext.replace('\t', ' ')
        if data and (data[-1].endswith('\n') or data[-1].endswith(' ')):
            ntext = ntext.lstrip(' ')
        elif ntext.startswith('  '):
            ntext = ' ' + ntext.lstrip(' ')
        if ntext.endswith('  '):
            ntext = ntext.rstrip(' ') + ' '
        if '  ' in ntext:
            ntext = re.sub(r'  +', ' ', ntext)
        return ntext

    def escape(self, ntext):
        if not self.vk_links:
            return ntext
        return ntext.replace('@', '&#64;').replace('(', '&#40;').replace(')', '&#41;').replace('*', '&#42;').replace('[', '&#91;').replace(']', '&#93;')

    def process_a(self, item, data, depth, with_cutted):
        if self.fancy and item.get('title') == "Читать дальше":
            # Кнопку ката пропускаем (её можно сделать фейковой, поэтому can_next = True)
            return []

        href = item.get('href')
        if self.vk_links and href and 'vk.com/' in href:
            g = re.match(r'^(https?:)?//([\.A-z0-9_-]+\.)?vk\.com/([A-z0-9_-]+)$', href)
            path = g.groups()[2] if g else None
            for stopword in ("wall", "photo", "page", "video", "videos", "audio", "audios", "topic", "app", "album", "note"):
                if not path or (
                    len(path) > len(stopword) and
                    path.startswith(stopword) and
                    (path[len(stopword)].isdigit() or path[len(stopword)] == '-')
                ):
                    return self.element_children(item, noblock=True)

            stop_cut, tmp = self.format_part(item, with_cutted)
            if not tmp.strip():
                return self.element_children(item, noblock=True)

            data.append(' @' + path + ' (')
            data.append(self.escape(tmp))
            data.append(') ')
            return None if stop_cut else []

        stop_cut, tmp = self.format_part(item, with_cutted)
        if self.disable_links and (
            tmp == href or
            href.find('://') < 7 and tmp == href[href.find('://') + 3:] or
            href.startswith('//') and tmp == href[2:]
        ):
            return None if stop_cut else []

        return self.element_children(item, noblock=True)

    def process_span(self, item, data, depth, with_cutted):
        if not self.fancy:
            return self.element_children(item, noblock=True)

        if item.get('class') == 'spoiler-title':
            # Заголовок спойлера опускаем всегда
            return []

        if item.get('class') == 'spoiler-body':
            # Тело спойлера опускаем, только если оно фейковое
            if depth[-1].tag != 'span' or depth[-1].get('class') != 'spoiler':
                return []
            ch = self.element_children(item, noblock=True)
            if ch:
                # Имитируем display: block
                ch.insert(0, self.NEWLINE)
                ch.append(self.NEWLINE)
            else:
                ch.append(self.NEWLINE)
            return ch
        return self.element_children(item, noblock=True)

    def process_li(self, item, data, depth, with_cutted):
        ch = [self.NEWLINE, '• ']
        ch.extend(self.element_children(item, noblock=True))
        ch.append(self.NEWLINE)
        return ch

    def process_blockquote(self, item, data, depth, with_cutted):
        ch = [self.NEWLINE, '«']
        ch.extend(self.element_children(item, noblock=True))
        ch.append('»')
        ch.append(self.NEWLINE)
        return ch

    def process_hr(self, item, data, depth, with_cutted):
        return [self.NEWLINE, '=====', self.NEWLINE]

    def process_s(self, item, data, depth, with_cutted):
        if self.strike_mode == 'unicode':
            # Без рекурсии никак :(
            stop_cut, tmp = self.format_part(item, with_cutted)
            tmp2 = []
            for x in tmp:
                tmp2.append(x)
                tmp2.append('\u0336')
            result = ''.join(tmp2)
            data.append(result)
            return None if stop_cut else []

        elif self.strike_mode == 'html':
            result = ['<s>']
            result.extend(self.element_children(item, noblock=True))
            result.append('</s>')
            return result

        else:
            return self.element_children(item, noblock=True)


def htmlToString(node, with_cutted=True, fancy=True, vk_links=False, hr_lines=True, disable_links=False):
    import warnings
    warnings.warn('utils.htmlToString is deprecated; use utils.HTMLFormatter instead of it', FutureWarning, stacklevel=2)

    if isinstance(node, text_types):
        return text(node)

    data = ""
    newlines = 0

    if node.text:
        ndata = node.text.replace("\n", " ")
        if newlines:
            ndata = ndata.lstrip()
        data += ndata
        if ndata:
            newlines = 0

    prev_text = None
    prev_after = None
    for item in node.iterchildren():
        if prev_text:
            ndata = prev_text.replace("\n", " ")
            if newlines:
                ndata = ndata.lstrip()
            data += ndata
            if ndata:
                newlines = 0
        if prev_after:
            ndata = prev_after.replace("\n", " ")
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
                data += "\n"
                newlines += 1
        elif item.tag == "hr":
            if hr_lines:
                data += "\n=====\n"
            else:
                data += "\n"
            newlines = 1
        elif fancy and item.get('class') == 'spoiler-title':
            prev_text = None
            continue
        elif fancy and item.tag == 'a' and item.get('title') == "Читать дальше":
            prev_text = None
            continue
        elif not with_cutted and is_cut(item):
            return data.strip()
        elif item.tag in ("img",):
            continue

        elif vk_links and item.tag == "a" and item.get('href', '').find("://vk.com/") > 0 and item.text_content().strip():
            href = item.get('href')
            addr = href[href.find("com/") + 4:]
            if addr and addr[-1] in (".", ")"):
                addr = addr[:-1]

            stop = False
            for c in ("/", "?", "&", "(", ",", ")", "|"):
                if c in addr:
                    stop = True
                    break
            if stop:
                data += item.text_content()
                prev_text = None
                continue

            for typ in ("wall", "photo", "page", "video", "topic", "app", "album", "note"):
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
                data += "• "
            elif data and item.tag in block_elems and not newlines:
                data += "\n"
                newlines = 1

            if prev_text:
                prev_text = None

            tmp = htmlToString(item, with_cutted=with_cutted, fancy=fancy, vk_links=vk_links, hr_lines=hr_lines)
            newlines = 0

            if item.tag == "s":  # зачёркивание
                tmp1 = ""
                for x in tmp:
                    tmp1 += x + '\u0336'
                # tmp1 = "<s>" + tmp1 + "</s>"
            elif item.tag == "blockquote":  # цитата
                tmp1 = " «" + tmp + "»\n"
                newlines = 1
            else:
                tmp1 = tmp

            data += tmp1

            if not with_cutted:
                for item2 in item.iterchildren():
                    if is_cut(item2):
                        return data.strip()

            if item.tag in block_elems and not newlines:
                data += "\n"
                newlines = 1

    if prev_text:
        ndata = prev_text.replace("\n", " ")
        if newlines:
            ndata = ndata.lstrip()
        data += ndata
        if ndata:
            newlines = 0
    if prev_after:
        ndata = prev_after.replace("\n", " ")
        if newlines:
            ndata = ndata.lstrip()
        data += ndata
        if ndata:
            newlines = 0

    return data.strip()


def node2string(node, encoding="utf-8"):
    """Переводит html-элемент в байтовую строку."""
    return lxml.etree.tostring(node, method="html", encoding=encoding)  # pylint: disable=no-member


def mon2num(s):
    """Переводит названия месяцев в числа, чтобы строку можно было скормить в strftime."""
    for i in range(len(mons)):
        s = s.replace(mons[i], text(i + 1))
    return s


def is_cut(item):
    """Возвращает True, если тег похож на кат (на момент написания это ``<a></a>``)."""
    return item.tag == "a" and not item.get("href") and not item.text_content() and not item.getchildren()


def find_images(body, spoiler_title=True, no_other=False):
    """Ищет картинки в lxml-элементе и возвращает их список в виде
    [[ссылки до ката], [ссылки после ката]].

    :param bool spoiler_title: включать ли картинки с заголовков спойлеров
    :param bool no_other: исключать ли всякий мусор. Фильтрация простейшая:
      по наличию "smile" или "gif" в ссылке, также убираются табунские аватарки
      и навигация АльтерБРЕДаций.
    :rtype: [list, list]
    """

    imgs = [[], []]
    links = [[], []]

    start = False
    for item in body.iterchildren():
        # FIXME: не работает, если кат внутри другого тега
        if not start and is_cut(item):
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
                if src[-4:].lower() not in ('jpeg', '.jpg', '.png'):
                    continue
            if "<" in src:
                continue
            if no_other and (
                ".gif" in src.lower() or
                "smile" in src.lower() or
                ("/avatar_" in src and '/images/' in src) or
                src.endswith('1_Prev.png') or src.endswith('2_Clear.png') or
                src.endswith('3_VK.png') or src.endswith('4_New.png') or
                src.endswith('5_Next.png')  # АБД
            ):
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
def encode_multipart_formdata(fields, files, boundary=None):
    """Возвращает кортеж (content_type, body), готовый для отправки HTTP POST--запроса.

    Значения полей и файлов могут быть строками (закодируются в utf-8),
    bytes или числами (будут преобразованы в строку).

    :param fields: простые поля запроса
    :type fields: коллекция кортежей (название, значение) или словарь
    :param fields: файлы запроса (MIME-тип будет выбран по расширению)
    :type fields: коллекция кортежей (название, имя файла, значение)
    :param boundary: boundary (по умолчанию генерируется случайные)
    :type boundary: строка или bytes
    :rtype: (строка, bytes)
    """

    if isinstance(fields, dict):
        fields = fields.items()
    if boundary is None:
        boundary = b'----------' + md5((text(int(time.time())) + text(random.randrange(1000))).encode('utf-8')).hexdigest().encode('utf-8')
    elif isinstance(boundary, text):
        boundary = boundary.encode('utf-8')
    L = []

    for (key, value) in fields:
        key = text(key).encode('utf-8')
        if isinstance(value, text):
            value = value.encode('utf-8')
        elif isinstance(value, (int, float, complex)):
            value = text(value).encode('utf-8')
        elif not isinstance(value, binary):
            raise ValueError('Value should be bytes, not %s' % type(value))
        L.append(b'--' + boundary)
        L.append(('Content-Disposition: form-data; name="%s"' % key.decode('utf-8')).encode('utf-8'))
        L.append(b'')
        L.append(value)

    for (key, filename, value) in files:
        key = text(key).encode('utf-8')
        filename = text(filename).encode('utf-8')
        if isinstance(value, text):
            value = value.encode('utf-8')
        elif not isinstance(value, binary):
            raise ValueError('Value should be bytes, not %s' % type(value))
        L.append(b'--' + boundary)
        L.append((
            'Content-Disposition: form-data; name="%s"; filename="%s"' % (key.decode('utf-8'), filename.decode('utf-8'))
        ).encode('utf-8'))
        L.append(('Content-Type: %s' % get_content_type(filename.decode('utf-8'))).encode('utf-8'))
        L.append(b'')
        L.append(value)

    L.append(b'--' + boundary + b'--')
    L.append(b'')
    body = b'\r\n'.join(L)
    content_type = 'multipart/form-data; boundary=%s' % boundary.decode('utf-8')
    return content_type, body


def get_content_type(filename):
    """return mimetypes.guess_type(filename)[0] or 'application/octet-stream'"""
    return text(mimetypes.guess_type(filename)[0] or 'application/octet-stream')


def send_form(url, fields, files, timeout=None, headers=None):
    """Отправляет форму, пользуясь функцией :func:`~tabun_api.utils.encode_multipart_formdata`.

    Значения полей и файлов могут быть строками (закодируются в utf-8),
    bytes или числами (будут преобразованы в строку).

    :param fields: простые поля запроса
    :type fields: коллекция кортежей (название, значение)
    :param fields: файлы запроса (MIME-тип будет выбран по расширению)
    :type fields: коллекция кортежей (название, имя файла, значение)
    :param float timeout: сколько ожидать ответа, не дождётся - кидается исключением urllib
    :param headers: дополнительные HTTP-заголовки (повторяться не могут)
    :type headers: кортежи из двух строк/bytes или словарь
    :rtype: ``urllib.addinfourl`` / ``urllib.response.addinfourl``
    """

    content_type, data = encode_multipart_formdata(fields, files)

    if not isinstance(url, urequest.Request):
        if PY2 and isinstance(url, text):
            url = url.encode('utf-8')
        url = urequest.Request(url)

    if isinstance(headers, dict):
        headers = headers.items()
    if headers:
        for header, value in headers:
            if not isinstance(header, str):  # py2 and py3
                header = str(header)
            if isinstance(value, text):
                value = value.encode('utf-8')
            url.add_header(header, value)
    url.add_unredirected_header(str('Content-type'), content_type.encode('utf-8'))
    url.data = data

    if timeout is None:
        return urequest.urlopen(url)
    else:
        return urequest.urlopen(url, timeout=timeout)


def find_substring(s, start, end, extend=False, with_start=True, with_end=True):
    """Возвращает подстроку, находящуюся между кусками строки ``start`` и ``end``,
    или ``None``, если не нашлось.

    При ``extend=True`` кусок строки end ищется с конца (``rfind``).
    """

    f1 = s.find(start)
    if f1 < 0:
        return
    f2 = (s.rfind if extend else s.find)(end, f1 + len(start))
    if f2 < 0:
        return
    return s[f1 + (0 if with_start else len(start)):f2 + (len(end) if with_end else 0)]


def download(url, maxmem=20 * 1024 * 1024, timeout=5, waitout=15):
    """Скачивает данные по ссылке. Имеет защиту от переполнения памяти
    и слишком долгого ожидания, чтобы всякие боты тут не висли.
    В случае чего кидает ``IOError``.

    :param url: ссылка, которую скачать
    :type url: строка
    :param int maxmem: допустимый максимальный размер скачиваемых данных
    :param float timeout: как долго можно ждать ответа
    :param float waitout: как долго можно скачивать данные
      (простенькая защита от Slow TCP DoS Attack — timeout тут не поможет)
    :rtype: bytes
    """

    # TODO: non-ASCII URL

    url = text(url)
    if url.startswith('//'):
        url = 'http:' + url
    req = urequest.urlopen(url.encode("utf-8") if PY2 else url, timeout=timeout)

    size = req.headers.get('content-length')
    if size and size.isdigit() and int(size) > maxmem:
        raise IOError("Too big")

    data = b''
    start_dwnl = time.time()

    while 1:
        if len(data) > maxmem:
            raise IOError("Too big")
        tmp = req.read(64 * 1024)
        if not tmp:
            break
        data += tmp
        if time.time() - start_dwnl >= waitout:
            raise IOError("Too long")
    req.close()

    return data


def find_good_image(urls, maxmem=20 * 1024 * 1024):
    """Ищет годную картинку из предложенного списка ссылок и возвращает ссылку
    и скачанные данные картинки (файл, bytes).
    Такой простенький фильтр смайликов и элементов оформления поста по размеру.

    Требует PIL или Pillow.

    Не грузит картинки размером больше maxmem байт, дабы не вылететь от
    нехватки памяти.
    """

    try:
        from PIL import Image
    except ImportError:
        import Image
    from io import BytesIO

    good_image = None, None
    for url in urls:
        url = text(url)
        if url.find('//dl.dropboxusercontent.com/') in (5, 6):
            waitout = 60
        elif url.find('//dl.dropbox.com/') in (5, 6):
            waitout = 60
        else:
            waitout = 15
        try:
            data = download(url, maxmem, waitout=waitout)
        except IOError:
            continue

        try:
            img = Image.open(BytesIO(data))
        except:
            continue

        if img.size[0] < 100 or img.size[1] < 100:
            continue
        good_image = url, data
        break

    return good_image


def generate_comments_tree(comms):
    """Строит дерево комментариев из словаря, возвращаемого функциями get_comments[_from].

    Формат элемента: [(комментарий, элемент), (комментарий, элемент), ...]

    Возвращает само такое дерево и список номеров комментариев-сирот
    (по идее должен быть пустой, но мало ли).

    :param comms: словарь комментариев
    :type comms: {id: :func:`~tabun_api.Comment`}
    :rtype: (list, list)
    """

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
    """Парсит ссылку на аватарку и возвращает id пользователя,
    дату отправки, размер, расширение и какой-то номер с конца ссылки.
    Если не удалось распарсить, то всё ``None``.

    :param url: ссылка
    :type url: строка
    :rtype: (int, "YYYY-MM-DD", (int, int), строка, int или None)
    """

    match = ava_regex.search(url)
    if not match:
        return None, None, None, None, None
    g = match.groups()
    user_id = int(g[3] + g[4] + g[5])
    date = g[6] + "-" + g[7] + "-" + g[8]
    size = (int(g[9]), int(g[10]))
    ext = g[11]
    num = int(g[13]) if g[13] is not None else None

    return user_id, date, size, ext, num


def decode_cf_email(data):
    key = int(data[0:2], 16)
    use_bytes = not isinstance(data, text)
    result = b''
    for i in range(1, len(data) // 2):
        b = int(data[i * 2:i * 2 + 2], 16) ^ key
        if PY2:
            result += chr(b)
        else:
            result += bytes([b])
    return result if use_bytes else result.decode('utf-8')


def replace_cloudflare_emails(data):
    """Декодирует почты, которые зашифровал CloudFlare, в html-странице."""
    r = cf_email if isinstance(data, text) else cf_email_b
    return r.sub(lambda x: decode_cf_email(x.groups()[0]), data)


def normalize_body(body=None, raw_body=None, cls='text'):
    """Кодирует lxml-элемент в исходник html или наоборот декодирует исходник в lxml-элемент."""
    if body is not None and raw_body is None:
        raw_body = lxml.etree.tostring(body, method="xml", encoding="utf-8")  # pylint: disable=no-member
        raw_body = raw_body.replace(b'&#13;', b'\r').decode('utf-8')
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

    return body, text(raw_body) if raw_body is not None else None


def escape_topic_contents(data, may_be_short=False):
    """Экранирует содержимое постов для защиты от поехавшей вёрстки и багов lxml."""
    if not isinstance(data, binary):
        # '\xa0'.strip() => ''
        # b'\xa0'.strip() => b'\xa0' — придерживаюсь этого варианта
        raise ValueError('data should be bytes')
    f1 = 0
    f2 = 0
    last_end = 0
    buf = []
    while True:
        # определяем границы тела очередного поста
        f1 = data.find(b'<div class="topic-content text">', last_end)
        if f1 < 0:
            break
        f2 = data.find(b'<footer', f1)
        if f2 < 0:
            break
        f2 = data.rfind(b'</div>', f1, f2)
        if f2 < 0:
            break

        # старые топики-ссылки
        if data.rfind(b'<div class="topic-url"', f1, f2) > 0:
            f2 = data.rfind(b'</div>', f1, data.rfind(b'<div class="topic-url"', f1, f2))
            if f2 < 0:
                break

        # топики-файлы
        if data.rfind(b'<div class="download"', f1, f2) > 0:
            f2 = data.rfind(b'</div>', f1, data.rfind(b'<div class="download"', f1, f2))
            if f2 < 0:
                break

        # выясняем, есть кат или нет
        body = data[data.find(b'>', f1) + 1:f2].strip()
        short = None
        if may_be_short:
            fa = body.rfind('title="Читать дальше">'.encode('utf-8'))
            if fa > 0:
                fa2 = body.find(b'</a>', fa)
                if fa2 > 0 and fa2 == len(body) - 4:
                    short = body[body.find(b">", fa) + 1:fa2].strip()
                    body = body[:body.rfind(b'<', 0, fa)].rstrip()

        # выпиливаем header при его наличии
        if body.startswith(b'<header'):
            body = body[body.find(b'</header>') + 9:].lstrip()

        # экранируем тело
        body = body.replace(b'&', b'&amp;').replace(b'<', b'&lt;').replace(b'>', b'&gt;').replace(b'"', b'&quot;')

        # собираем страницу обратно
        buf.extend((
            data[last_end:f1],
            ('<div class="topic-content text" data-escaped="1" data-short="%s" data-short-text="%s">' % (
                1 if short is not None else 0, short.decode('utf-8') if short is not None else ''
            )).encode('utf-8'),
            body,
            b'</div>'
        ))
        last_end = f2 + 6

    buf.append(data[last_end:])
    return b''.join(buf)


def escape_comment_contents(data):
    """Экранирует содержимое комментов."""
    if not isinstance(data, binary):
        raise ValueError('data should be bytes')
    f1 = 0
    f2 = 0
    last_end = 0
    buf = []

    while True:
        # определяем границы очередного коммента
        sect_start = data.find(b'<section', last_end)
        if sect_start < 0:
            break
        sect_end = data.find(b'</section>', sect_start)
        if sect_end < 0:
            break

        prev_last_end = last_end
        last_end = sect_end

        if data.find(b'class="comment ', sect_start, sect_end) < 0 and data.find(b'class="comment"', sect_start, sect_end) < 0 and data.find(b'class="comment\n', sect_start, sect_end) < 0:
            # не коммент
            buf.append(data[prev_last_end:last_end])
            continue

        # Выделяем текст коммента
        f1 = data.find(b'class="comment-content">', sect_start, sect_end)
        if f1 >= 0:
            f = data.find(b'<div class=" text">', f1, f1 + 150)
            if f < 0:
                f1 = data.find(b'<div class="text">', f1, f1 + 150)
            else:
                f1 = f
            del f
        if f1 < 0:
            # Коммент без текста (например, удалённый)
            buf.append(data[prev_last_end:last_end])
            continue

        # Блок редактирования (в отключенном плагине)
        f2 = data.rfind(b'<div id="info_edit_', f1, sect_end)

        # Путь к посту на странице /comments/
        if f2 < 0:
            f2 = data.rfind(b'<div class="comment-path', f1, sect_end)

        # Информация о комменте в самом посте
        if f2 < 0:
            f2 = data.rfind(b'<ul class="comment-info', f1, sect_end)

        if f2 < 0:
            # Что-то совсем битое, вроде скрытого заминусованного коммента
            buf.append(data[prev_last_end:last_end])
            continue

        # Обходим </div> от <div class="comment-content">
        f2 = data.rfind(b'</div>', f1, f2)
        if f2 >= 0:
            f2 = data.rfind(b'</div>', f1, f2)
        if f2 < 0:
            print('Warning: cannot find </div></div>! Please report to andreymal.')
            buf.append(data[prev_last_end:last_end])
            continue

        # экранируем тело
        body = data[data.find(b'>', f1, f2) + 1:f2].strip()
        body = body.replace(b'&', b'&amp;').replace(b'<', b'&lt;').replace(b'>', b'&gt;').replace(b'"', b'&quot;')

        # собираем страницу обратно
        buf.extend((
            data[prev_last_end:f1],
            b'<div class="text" data-escaped="1">',
            body,
            data[f2:last_end]
        ))

    buf.append(data[last_end:])
    return b''.join(buf)


def parse_datetime(s, utc=True):
    """Парсит дату-время в формате ISO 8601 и возвращает объект datetime с часовым поясом.
    При utc=True возвращает время в UTC (без привязки к часовому поясу для совместимости с Python 2),
    иначе — что распарсилось.
    """

    tm = iso8601.parse_date(s)
    if not utc:
        return tm
    return (tm - tm.utcoffset()).replace(tzinfo=None)


def gen_user_agent():
    """Генерирует кусочек юзерагента с информаией о системе."""
    # pylint: disable=E1101
    context = {
        'system': platform.system() or 'NA',
        'machine': platform.machine() or 'NA',
        'release': platform.release() or 'NA',
        'pyi': platform.python_implementation() or 'Python',
        'pyv': platform.python_version(),
        'pyiv': platform.python_version(),
        'urv': urequest.__version__,
    }
    if context['pyi'] == 'PyPy':
        context['pyiv'] = '{}.{}.{}'.format(
            sys.pypy_version_info.major,
            sys.pypy_version_info.minor,
            sys.pypy_version_info.micro,
        )
        if sys.pypy_version_info.releaselevel != 'final':
            context['pyiv'] = context['pyiv'] + sys.pypy_version_info.releaselevel

    return '({system} {machine} {release}) Python/{pyv} {pyi}/{pyiv} urllib/{urv}'.format(**context)
