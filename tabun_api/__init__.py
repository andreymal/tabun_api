#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

import os
import re
import time
from socket import timeout as socket_timeout
from json import JSONDecoder
from threading import RLock

from . import utils, compat
from .compat import PY2, BaseCookie, urequest, text_types, text, binary


__version__ = '0.6.3'

#: Адрес Табуна. Именно на указанный здесь адрес направляются запросы.
http_host = "http://tabun.everypony.ru"

#: Список полузакрытых блогов. В tabun_api нигде не используется, но может использоваться в использующих его программах.
halfclosed = ("borderline", "shipping", "erpg", "gak", "RPG", "roliplay", "tearsfromthemoon", "Technic")

#: Заголовки для HTTP-запросов. Возможно, стоит менять user-agent.
http_headers = {
    "connection": "close",
    "user-agent": "tabun_api/%s; Linux/2.6" % __version__
}

#: Регулярка для парсинга ссылки на пост.
post_url_regex = re.compile(r"/blog/(([A-z0-9_\-\.]{1,})/)?([0-9]{1,}).html")

#: Регулярка для парсинга прикреплённых файлов.
post_file_regex = re.compile(r'^Скачать \"(.+)" \(([0-9]*(\.[0-9]*)?) (Кб|Мб)\)$')


class NoRedirect(urequest.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp

    http_error_301 = http_error_303 = http_error_307 = http_error_302


class TabunError(Exception):
    """Общее для библиотеки исключение.
    Содержит атрибут code с всякими разными циферками для разных типов исключения, обычно совпадает с HTTP-кодом ошибки при запросе.
    А в атрибуте message или текст, или снова код ошибки.
    """
    def __init__(self, msg=None, code=0, data=None):
        self.code = int(code)
        self.message = text(msg) if msg else text(code)
        self.data = data
        Exception.__init__(self, self.message.encode("utf-8"))

    def __str__(self):
        return self.message.encode("utf-8") if PY2 else self.message

    def __unicode__(self):
        return self.message


class TabunResultError(TabunError):
    """Исключение, содержащее текст ошибки, который вернул сервер. Как правило, это текст соответствующих всплывашек на сайте."""
    pass


class Post(object):
    """Пост."""
    def __init__(self, time, blog, post_id, author, title, draft,
                 vote_count, vote_total, body, tags, comments_count=None, comments_new_count=None,
                 short=False, private=False, blog_name=None, poll=None, favourite=0, favourited=False,
                 download=None, raw_body=None):
        self.time = time
        self.blog = text(blog) if blog else None
        self.post_id = int(post_id)
        self.author = text(author)
        self.title = text(title)
        self.draft = bool(draft)
        self.vote_count = int(vote_count) if vote_count is not None else None
        self.vote_total = int(vote_total) if vote_total is not None else None
        self.tags = tags
        self.comments_count = int(comments_count) if comments_count is not None else None
        self.comments_new_count = int(comments_new_count) if comments_new_count is not None else None
        self.short = bool(short)
        self.private = bool(private)
        self.blog_name = text(blog_name) if blog_name else None
        self.poll = poll
        self.favourite = int(favourite) if favourite is not None else None
        self.favourited = bool(favourited)
        if download and (not isinstance(download, Download) or download.post_id != self.post_id):
            raise ValueError
        self.download = download

        self.body, self.raw_body = utils.normalize_body(body, raw_body, cls='topic-content text')

    def __repr__(self):
        o = "<post " + ((self.blog + "/") if self.blog else "personal ") + text(self.post_id) + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')

    @property
    def url(self):
        return http_host + '/blog/' + ((self.blog + '/') if self.blog else '') + text(self.post_id) + '.html'


class Download(object):
    """Прикрепленный к посту файл (в новом Табуне) или ссылка (в старом Табуне)."""
    def __init__(self, type, post_id, filename, count, filesize=None):
        self.type = text(type)
        if self.type not in ("file", "link"):
            raise ValueError
        self.post_id = int(post_id)
        self.filename = text(filename) if filename else None  # или ссылка
        self.filesize = int(filesize) if filesize is not None else None  # в байтах
        self.count = int(count)


class Comment(object):
    """Коммент. Возможно, удалённый, поэтому следите, чтобы значения не были None!"""
    def __init__(self, time, blog, post_id, comment_id, author, body, vote, parent_id=None,
                 post_title=None, unread=False, deleted=False, favourite=None, favourited=False,
                 raw_body=None):
        self.time = time
        self.blog = text(blog) if blog else None
        self.post_id = int(post_id) if post_id else None
        self.comment_id = int(comment_id)
        self.author = text(author) if author else None
        self.vote = int(vote) if vote is not None else None
        self.unread = bool(unread)
        if parent_id:
            self.parent_id = int(parent_id)
        else:
            self.parent_id = None
        if post_title:
            self.post_title = text(post_title)
        else:
            self.post_title = None
        self.deleted = bool(deleted)
        self.favourite = int(favourite) if favourite is not None else None
        self.favourited = bool(favourited)

        self.body, self.raw_body = utils.normalize_body(body, raw_body)

    def __repr__(self):
        o = (
            "<" + ("deleted " if self.deleted else "") + "comment " +
            ((self.blog + "/" + text(self.post_id) + "/") if self.blog and self.post_id else "") +
            text(self.comment_id) + ">"
        )
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')


class Blog(object):
    """Блог."""
    def __init__(self, blog_id, blog, name, creator, readers=0, rating=0.0, closed=False,
                 description=None, admins=None, moderators=None, vote_count=-1, posts_count=-1,
                 created=None, raw_description=None):
        self.blog_id = int(blog_id)
        self.blog = text(blog)
        self.name = text(name)
        self.creator = text(creator)
        self.readers = int(readers)
        self.rating = int(rating)
        self.closed = bool(closed)
        self.admins = admins
        self.moderators = moderators
        self.vote_count = int(vote_count)
        self.posts_count = int(posts_count)
        self.created = created

        self.description, self.raw_description = utils.normalize_body(description, raw_description)

    def __repr__(self):
        o = "<blog " + self.blog + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')

    @property
    def url(self):
        return http_host + '/blog/' + self.blog + '/'


class StreamItem(object):
    """Элемент «Прямого эфира»."""
    def __init__(self, blog, blog_title, title, author, comment_id, comments_count):
        self.blog = text(blog) if blog else None
        self.blog_title = text(blog_title)
        self.title = text(title)
        self.author = text(author)
        self.comment_id = int(comment_id)
        self.comments_count = int(comments_count)

    def __repr__(self):
        o = "<stream_item " + ((self.blog + "/") if self.blog else '') + text(self.comment_id) + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8')


class UserInfo(object):
    """Информация о броняше."""
    def __init__(self, user_id, username, realname, skill, rating, userpic=None, foto=None,
                 gender=None, birthday=None, registered=None, last_activity=None,
                 description=None, blogs=None, raw_description=None):
        self.user_id = int(user_id)
        self.username = text(username)
        self.realname = text(realname) if realname else None
        self.skill = float(skill)
        self.rating = float(rating)
        self.userpic = text(userpic) if userpic else None
        self.foto = text(foto) if foto else None
        self.gender = gender if gender in ('M', 'F') else None
        self.birthday = birthday
        self.registered = registered
        self.last_activity = last_activity
        self.blogs = {}
        self.blogs['owner'] = blogs.get('owner', []) if blogs else []
        self.blogs['admin'] = blogs.get('admin', []) if blogs else []
        self.blogs['moderator'] = blogs.get('moderator', []) if blogs else []
        self.blogs['member'] = blogs.get('member', []) if blogs else []

        self.description, self.raw_description = utils.normalize_body(description, raw_description)

    def __repr__(self):
        o = "<userinfo " + self.username + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')


class Poll(object):
    """Опрос. Список items содержит кортежи (название ответа, процент проголосовавших, число проголосовавших)."""
    def __init__(self, total, notvoted, items):
        self.total = int(total)
        self.notvoted = int(notvoted)
        self.items = []
        for x in items:
            self.items.append((text(x[0]), float(x[1]), int(x[2])))


class TalkItem(object):
    """Личное сообщение."""
    def __init__(self, talk_id, recipients, unread, title, date, body=None, author=None, comments=None, raw_body=None):
        self.talk_id = int(talk_id)
        self.recipients = [text(x) for x in recipients]
        self.unread = bool(unread)
        self.title = text(title)
        self.date = date
        self.author = text(author) if author else None
        self.comments = comments if comments else []

        self.body, self.raw_body = utils.normalize_body(body, raw_body)

    def __repr__(self):
        o = "<talk " + text(self.talk_id) + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')


class ActivityItem(object):
    """Событие со страницы /stream/."""
    WALL_ADD = 0  # Просто чтобы было :)
    POST_ADD = 1
    COMMENT_ADD = 2
    BLOG_ADD = 3
    POST_VOTE = 11
    COMMENT_VOTE = 12
    BLOG_VOTE = 13
    USER_VOTE = 14
    FRIEND_ADD = 4
    JOIN_BLOG = 24

    def __init__(self, type, date, post_id=None, comment_id=None, blog=None, username=None, title=None, data=None, id=None):
        self.type = int(type)
        if self.type not in (
            self.WALL_ADD, self.POST_ADD, self.COMMENT_ADD, self.BLOG_ADD,
            self.POST_VOTE, self.COMMENT_VOTE, self.BLOG_VOTE,
            self.USER_VOTE, self.FRIEND_ADD, self.JOIN_BLOG
        ):
            raise ValueError

        self.date = date

        self.post_id = int(post_id) if post_id is not None else None
        self.comment_id = int(comment_id) if comment_id is not None else None
        self.blog = text(blog) if blog is not None else None
        self.username = text(username) if username is not None else None
        self.title = text(title) if title is not None else None
        self.data = text(data) if data is not None else None
        self.id = int(id) if id is not None else None

    def __str__(self):
        return "<activity " + text(self.type) + " " + (self.username or 'N/A') + ">"

    def __repr__(self):
        o = self.__str__()
        return o.encode('utf-8') if PY2 else o

    def __eq__(self, other):
        return (
            isinstance(other, ActivityItem) and
            self.type == other.type and
            self.date == other.date and
            self.post_id == other.post_id and
            self.comment_id == other.comment_id and
            self.blog == other.blog and
            self.username == other.username and
            self.title == other.title and
            self.data == other.data
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class User(object):
    """Через божественные объекты класса User осуществляется всё взаимодействие с Табуном.
    Почти все функции могут кидаться исключением TabunResultError с текстом ошибки (который на сайте обычно показывается во всплывашке в углу).

    Допустимые комбинации параметров (в квадратных скобках опциональные):

    * login + passwd [ + phpsessid]
    * phpsessid [+ key] - без куки key разлогинивает через некоторое время
    * login + phpsessid + security_ls_key [+ key] (без запроса к серверу)
    * без параметров (анонимус)

    Если у функции есть параметр raw_data, то через него можно передать код страницы, чтобы избежать лишнего запроса к Табуну.
    Если есть параметр url, то при его указании открывается именно указанный url вместо формирования стандартного с помощью других параметров функции.

    phpsessid - печенька (cookie), по которой идентифицируется пользователь (на самом Табуне называется TABUNSESSIONID).
    security_ls_key - секретный ключ движка LiveStreet для отправки запросов.
    key - печенька неизвестного мне назначения.
    Можно не париться с ними, их автоматически пришлёт сервер во время инициализации объекта.
    А можно, например, не авторизоваться по логину и паролю, а выдрать из браузера печеньку TABUNSESSIONID, скормить в аргумент phpsessid и авторизоваться через неё.

    Конструктор также принимает кортеж proxy из трёх элементов (тип, хост, порт) для задания прокси-сервера. Сейчас поддерживаются только типы socks4 и socks5.
    Вместо передачи параметра можно установить переменную окружения TABUN_API_PROXY=тип,хост,порт — конструктор её подхватит.

    Если нужно парсить не Табун (можно частично парсить другие LiveStreet-сайты с основанным на synio шаблоном), то можно передать http_host,
    чтобы не переопределять его во всём tabun_api.

    У класса также есть следующие поля:

    * username — имя пользователя или None
    * talk_unread — число непрочитанных личных сообщений (после update_userinfo)
    * skill — силушка (после update_userinfo)
    * rating — кармушка (после update_userinfo)
    * timeout — таймаут ожидания ответа от сервера (для функции urlopen, по умолчанию 20)
    * phpsessid, security_ls_key, key — ну вы поняли
    """

    phpsessid = None
    username = None
    security_ls_key = None
    key = None
    timeout = 20
    talk_unread = 0
    skill = None
    rating = None
    query_interval = 0
    proxy = None
    http_host = None
    session_cookie_name = 'TABUNSESSIONID'

    def __init__(self, login=None, passwd=None, phpsessid=None, security_ls_key=None, key=None, proxy=None, http_host=None):
        self.http_host = text(http_host).rstrip('/') if http_host else None

        self.jd = JSONDecoder()
        self.lock = RLock()

        handlers = []

        if proxy is None and os.getenv('TABUN_API_PROXY') and os.getenv('TABUN_API_PROXY').count(',') == 2:
            proxy = os.getenv('TABUN_API_PROXY').split(',')[:3]
        elif proxy:
            proxy = proxy.split(',') if isinstance(proxy, text_types) else list(proxy)[:3]

        if proxy:
            if not PY2:
                raise NotImplementedError("Python 2 only")
            if proxy[0] not in ('socks4', 'socks5'):
                raise NotImplementedError('I can use only socks proxies now')
            proxy[2] = int(proxy[2])
            import socks
            from socksipyhandler import SocksiPyHandler
            if proxy[0] == 'socks5':
                handlers.append(SocksiPyHandler(socks.PROXY_TYPE_SOCKS5, proxy[1], proxy[2]))
            elif proxy[0] == 'socks4':
                handlers.append(SocksiPyHandler(socks.PROXY_TYPE_SOCKS4, proxy[1], proxy[2]))
            self.proxy = proxy

        # for thread safety
        self.opener = urequest.build_opener(*handlers)
        self.noredir = urequest.build_opener(*(handlers + [NoRedirect]))

        if phpsessid:
            self.phpsessid = text(phpsessid).split(";", 1)[0]
        if key:
            self.key = text(key)
        if self.phpsessid and security_ls_key:
            self.security_ls_key = text(security_ls_key)
            if login:
                self.username = text(login)
            return

        if not self.phpsessid or not security_ls_key:
            resp = self.urlopen("/")
            data = resp.read(1024 * 25)
            resp.close()
            cook = BaseCookie()
            if PY2:
                cook.load(resp.headers.get("set-cookie") or b'')
            else:
                for x in resp.headers.get_all("set-cookie") or ():
                    cook.load(x)
            if not self.phpsessid:
                self.phpsessid = cook.get(self.session_cookie_name)
                if self.phpsessid:
                    self.phpsessid = self.phpsessid.value
            if not self.key:
                ckey = cook.get("key")
                self.key = ckey.value if ckey else None
            pos = data.find(b"var LIVESTREET_SECURITY_KEY =")
            if pos > 0:
                ls_key = data[pos:]
                ls_key = ls_key[ls_key.find(b"'") + 1:]
                self.security_ls_key = ls_key[:ls_key.find(b"'")].decode('utf-8', 'replace')

            if self.security_ls_key == b'LIVESTREET_SECURITY_KEY':  # security fix by Random
                csecurity_ls_key = cook.get("LIVESTREET_SECURITY_KEY")
                self.security_ls_key = csecurity_ls_key.value if csecurity_ls_key else None

            self.update_userinfo(data)

        if login and passwd:
            self.login(login, passwd)

        self.last_query_time = 0
        self.talk_count = 0

    def update_userinfo(self, raw_data):
        """Парсит имя пользователя, рейтинг и число непрочитанных сообщений
        с переданного кода страницы и записывает в объект.
        Возвращает имя пользователя или None при его отсутствии.
        """
        userinfo = utils.find_substring(raw_data, b'<div class="dropdown-user"', b"<nav", with_end=False)
        if not userinfo:
            auth_panel = utils.find_substring(raw_data, b'<ul class="auth"', b'<nav', with_end=False)
            if auth_panel and 'Войти'.encode('utf-8') in auth_panel:
                self.username = None
                self.talk_count = 0
                self.skill = None
                self.rating = None
            else:
                print("Warning: update_userinfo received unknown data")
            return

        node = utils.parse_html_fragment(userinfo)[0]
        dd_user = node.xpath('//*[@id="dropdown-user"]')
        if not dd_user:
            self.username = None
            self.talk_count = 0
            self.skill = None
            self.rating = None
            return
        dd_user = dd_user[0]

        username = dd_user.xpath('a[2]/text()[1]')
        if username and username[0]:
            self.username = username[0]
        else:
            self.username = None
            self.talk_count = 0
            self.skill = None
            self.rating = None
            return

        talk_count = dd_user.xpath('ul/li[@class="item-messages"]/a[@class="new-messages"]/text()')
        if not talk_count:
            self.talk_unread = 0
        else:
            self.talk_unread = int(talk_count[0][1:])

        strength = dd_user.xpath('ul[@class="dropdown-user-menu"]/li/span/text()')
        if not strength:
            self.skill = 0.0
        else:
            self.skill = float(strength[0])

        if len(strength) < 2:
            self.rating = 0.0
        else:
            self.rating = float(strength[1])

        return self.username

    def login(self, login, password, return_path=None, remember=True):
        """Логинится и записывает печеньку key в случае успеха. Параметр return_path нафиг не нужен, remember - галочка «Запомнить меня»."""
        login = text(login)
        password = text(password)
        query = "login=" + urequest.quote(login.encode('utf-8'))
        query += "&password=" + urequest.quote(password.encode('utf-8'))
        query += "&remember=" + ("on" if remember else "off")
        query += "&return-path=" + urequest.quote(return_path if return_path else (self.http_host or http_host) + "/")
        if self.security_ls_key:
            query += "&security_ls_key=" + urequest.quote(self.security_ls_key)

        resp = self.urlopen("/login/ajax-login", query, {"X-Requested-With": "XMLHttpRequest", "content-type": "application/x-www-form-urlencoded"})
        data = resp.read()
        if data[0] not in (b"{", 123):
            raise TabunResultError(data.decode("utf-8", "replace"))
        data = self.jd.decode(data.decode('utf-8'))
        if data.get('bStateError'):
            raise TabunResultError(data.get("sMsg", ""))
        self.username = login

        cook = BaseCookie()
        cook.load(resp.headers.get("set-cookie", ""))
        ckey = cook.get("key")
        self.key = ckey.value if ckey else None

    def check_login(self):
        """Генерирует исключение, если нет phpsessid или security_ls_key."""
        if not self.phpsessid or not self.security_ls_key:
            raise TabunError("Not logined")

    def build_request(self, url, data=None, headers=None, with_cookies=True):
        """Собирает и возвращает объект Request. Используется в методе urlopen."""

        if isinstance(url, binary):
            url = url.decode('utf-8')
        if not isinstance(url, urequest.Request):
            if url.startswith('/'):
                url = (self.http_host or http_host) + url
            url = urequest.Request(url.encode('utf-8') if PY2 else url)
        if data is not None:
            url.data = data.encode('utf-8') if isinstance(data, text) else data

        request_headers = dict(http_headers)
        if headers:
            request_headers.update(headers)

        if with_cookies and self.phpsessid:
            request_headers['Cookie'] = ("%s=%s; key=%s; LIVESTREET_SECURITY_KEY=%s" % (
                self.session_cookie_name, self.phpsessid, self.key, self.security_ls_key
            )).encode('utf-8')

        for header, value in request_headers.items():
            if not isinstance(header, str):  # py2 and py3
                header = str(header)
            if isinstance(value, text):
                value = value.encode('utf-8')
            url.add_header(header, value)

        return url

    def send_request(self, request, redir=True, nowait=False, timeout=None):
        """Отправляет запрос (строку со ссылкой или объект Request).
        Возвращает результат вызова urlopen (объект urllib.addinfourl).
        Используется в методе urlopen.
        """

        # FIXME: ну чего так некрасиво-то получилось?
        self.lock.acquire()
        try:
            while not nowait and self.query_interval > 0 and time.time() - self.last_query_time < self.query_interval:
                sleeptime = self.query_interval - time.time() + self.last_query_time
                if sleeptime > 0:
                    self.lock.release()
                    try:
                        time.sleep(sleeptime)
                    finally:
                        self.lock.acquire()

            self.last_query_time = time.time()

            if timeout is None:
                timeout = self.timeout

            try:
                return (self.opener.open if redir else self.noredir.open)(request, timeout=timeout)
            except KeyboardInterrupt:
                raise
            except urequest.HTTPError as exc:
                if exc.getcode() == 404:
                    data = exc.read(8192)
                    if b'//projects.everypony.ru/error/main.css' in data:
                        raise TabunError('Static 404', -404)
                raise TabunError(code=exc.getcode())
            except urequest.URLError as exc:
                raise TabunError(exc.reason, -exc.reason.errno if exc.reason.errno else 0)
            except compat.HTTPException as exc:
                raise TabunError("HTTP error", -4)
            except socket_timeout:
                raise TabunError("Timeout", -2)
            except IOError as exc:
                raise TabunError(text(exc), -3)

        finally:
            self.lock.release()

    def urlopen(self, url, data=None, headers=None, redir=True, nowait=False, with_cookies=True, timeout=None):
        """Отправляет HTTP-запрос и возвращает результат вызова urlopen (объект addinfourl).
        Если указан параметр data, то отправляется POST-запрос.
        В качестве URL может быть путь с доменом (http://tabun.everypony.ru/), без домена (/index/newall/) или объект Request.
        Если redir установлен в False, то не будет осуществляться переход по перенаправлению (HTTP-коды 3xx).
        К запросу добавлется печенька TABUNSESSIONID (из атрибута phpsessid); with_cookies=False отключает это.
        По умолчанию соблюдает между запросами временной интервал query_interval (который по умолчанию 0);
        при nowait=True запрос всегда отправляется немедленно.
        Может кидаться исключением TabunError.
        """

        req = self.build_request(url, data, headers, with_cookies)
        return self.send_request(req, redir, nowait, timeout)

    def send_form(self, url, fields=(), files=(), headers=None, redir=True):
        """Формирует multipart/form-data запрос и отправляет его через функцию urlopen."""
        content_type, data = utils.encode_multipart_formdata(fields, files)
        headers = dict(headers or ())
        headers['content-type'] = content_type
        return self.urlopen(url, data, headers, redir)

    def ajax(self, url, fields=None, files=(), headers=None, throw_if_error=True):
        """Отправляет ajax-запрос и возвращает распарсенный json-ответ. Или кидается исключением TabunResultError в случае ошибки."""
        self.check_login()
        headers = dict(headers or ())
        headers['x-requested-with'] = 'XMLHttpRequest'
        fields['security_ls_key'] = self.security_ls_key
        data = self.send_form(url, fields or {}, files, headers=headers).read()

        try:
            data = self.jd.decode(data.decode('utf-8'))
        except:
            raise TabunResultError(data.decode("utf-8", "replace"))

        if throw_if_error and data['bStateError']:
            raise TabunResultError(data['sMsg'], data=data)

        return data

    def add_post(self, blog_id, title, body, tags, draft=False, check_if_error=False):
        """Отправляет пост и возвращает имя блога с номером поста в случае удачи или (None,None) в случае неудачи.
        При check_if_error=True проверяет наличие поста по заголовку даже в случае ошибки (если, например, таймаут или 404, но пост, как иногда бывает, добавляется)."""
        self.check_login()
        blog_id = int(blog_id if blog_id else 0)

        if not isinstance(tags, text_types):
            tags = ", ".join(tags)

        fields = {
            'topic_type': 'topic',
            'security_ls_key': self.security_ls_key,
            'blog_id': text(blog_id),
            'topic_title': text(title),
            'topic_text': text(body),
            'topic_tags': text(tags)
        }
        if draft:
            fields['submit_topic_save'] = "Сохранить в черновиках"
        else:
            fields['submit_topic_publish'] = "Опубликовать"

        try:
            result = self.send_form('/topic/add/', fields, redir=False)
            data = result.read()
            error = utils.find_substring(data, b'<ul class="system-message-error">', b'</ul>', with_start=False, with_end=False)
            if error and b':' in error:
                error = utils.find_substring(error.decode('utf-8', 'replace'), ':', '</li>', extend=True, with_start=False, with_end=False).strip()
                raise TabunResultError(error)
            link = result.headers.get('location')
        except TabunError:
            if not check_if_error or not self.username:
                raise
            url = '/topic/saved/' if draft else '/profile/' + urequest.quote(self.username.encode('utf-8')) + '/created/topics/'

            try:
                posts = self.get_posts(url)
            except:
                posts = []
            posts.reverse()

            for post in posts[:2]:
                if posts and post.title == text(title) and post.author == self.username:
                    return post.blog, post.post_id

            raise
        else:
            return parse_post_url(link)

    def add_poll(self, blog_id, title, choices, body, tags, draft=False, check_if_error=False):
        """Создает опрос и возвращает имя блога с номером поста в случае удачи или
        (None, None)  случае неудачи.
        Вариантов ответов не может быть более 20 штук, иначе кидается исключение.
        При check_if_error=True проверяет наличие поста по заголовку даже в случае ошибки (если, например, таймаут или 404, но пост, как иногда бывает, добавляется)."""
        if len(choices) > 20:
            raise TabunError("Can't have more than 20 choices in poll, but had %d" % len(choices))

        self.check_login()
        blog_id = int(blog_id if blog_id else 0)

        if not isinstance(tags, text_types):
            tags = ", ".join(tags)

        fields = [
            ('topic_type', 'question'),
            ('security_ls_key', self.security_ls_key),
            ('blog_id', text(blog_id)),
            ('topic_title', text(title)),
            ('topic_text', text(body)),
            ('topic_tags', text(tags))
        ]
        for choice in choices:
            fields.append(('answer[]', choice))

        if draft:
            fields.append(('submit_topic_save', "Сохранить в черновиках"))
        else:
            fields.append(('submit_topic_publish', "Опубликовать"))

        try:
            result = self.send_form('/question/add/', fields, redir=False)
            data = result.read()
            error = utils.find_substring(data, b'<ul class="system-message-error">', b'</ul>', with_start=False, with_end=False)
            if error and b':' in error:
                error = utils.find_substring(error.decode('utf-8', 'replace'), ':', '</li>', extend=True, with_start=False, with_end=False).strip()
                raise TabunResultError(error)
            link = result.headers.get('location')
        except TabunError:
            if not check_if_error or not self.username:
                raise
            url = '/topic/saved/' if draft else '/profile/' + urequest.quote(self.username.encode('utf-8')) + '/created/topics/'

            try:
                posts = self.get_posts(url)
            except:
                posts = []
            posts.reverse()

            for post in posts[:2]:
                if posts and post.title == text(title) and post.author == self.username:
                    return post.blog, post.post_id

            return None, None
        else:
            return parse_post_url(link)

    def create_blog(self, title, url, description, rating_limit=0, closed=False):
        """Создаёт блог и возвращает его url-имя или None в случае неудачи."""
        self.check_login()

        fields = {
            'security_ls_key': self.security_ls_key,
            "blog_title": text(title),
            "blog_url": text(url),
            "blog_type": "close" if closed else "open",
            "blog_description": text(description),
            "blog_limit_rating_topic": text(int(rating_limit)),
            "submit_blog_add": "Сохранить"
        }

        link = self.send_form('/blog/add/', fields, redir=False).headers.get('location')
        if not link:
            return
        if link[-1] == '/':
            link = link[:-1]
        return link[link.rfind('/') + 1:]

    def edit_blog(self, blog_id, title, description, rating_limit=0, closed=False):
        """Редактирует блог и возвращает его url-имя или None в случае неудачи."""
        self.check_login()

        fields = {
            'security_ls_key': self.security_ls_key,
            "blog_title": text(title),
            "blog_url": "",
            "blog_type": "close" if closed else "open",
            "blog_description": text(description),
            "blog_limit_rating_topic": text(int(rating_limit)),
            "avatar_delete": "",
            "submit_blog_add": "Сохранить"
        }

        link = self.send_form('/blog/edit/' + text(int(blog_id)) + '/', fields, redir=False).headers.get('location')
        if not link:
            return
        if link[-1] == '/':
            link = link[:-1]
        return link[link.rfind('/') + 1:]

    def delete_blog(self, blog_id):
        """Удаляет блог и возвращает True/False в случае удачи/неудачи."""
        self.check_login()
        return self.urlopen(
            url='/blog/delete/' + text(int(blog_id)) + '/?security_ls_key=' + self.security_ls_key,
            headers={"referer": (self.http_host or http_host) + "/"},
            redir=False
        ).getcode() / 100 == 3

    def preview_post(self, blog_id, title, body, tags):
        """Возвращает HTML-код предпросмотра поста (сам пост плюс мусор типа заголовка «Предпросмотр»)."""
        self.check_login()

        fields = {
            'topic_type': 'topic',
            'security_ls_key': self.security_ls_key,
            'blog_id': text(blog_id),
            'topic_title': text(title),
            'topic_text': text(body),
            'topic_tags': text(tags)
        }

        data = self.send_form('/ajax/preview/topic/', fields, (), headers={'x-requested-with': 'XMLHttpRequest'}).read()
        node = utils.parse_html_fragment(data)[0]
        data = node.text
        result = self.jd.decode(data)
        if result['bStateError']:
            raise TabunResultError(result['sMsg'])
        return result['sText']

    def delete_post(self, post_id):
        """Удаляет пост и возвращает True/False в случае удачи/неудачи."""
        self.check_login()
        return self.urlopen(
            url='/topic/delete/' + text(int(post_id)) + '/?security_ls_key=' + self.security_ls_key,
            headers={"referer": (self.http_host or http_host) + "/blog/" + text(post_id) + ".html"},
            redir=False
        ).getcode() / 100 == 3

    def toggle_blog_subscribe(self, blog_id):
        """Подписывается на блог/отписывается от блога и возвращает новое состояние: True - подписан, False - не подписан."""
        return self.ajax('/blog/ajaxblogjoin/', {'idBlog': int(blog_id)})['bState']

    def comment(self, post_id, body, reply=0, typ="blog"):
        """Отправляет коммент и возвращает его номер. Тип - blog (посты) или talk (личные сообщения)"""
        fields = {
            'comment_text': text(body),
            'reply': int(reply),
            'cmt_target_id': int(post_id)
        }

        return self.ajax("/" + (typ if typ in ("blog", "talk") else "blog") + "/ajaxaddcomment/", fields)['sCommentId']

    def get_recommendations(self, raw_data):
        """Возвращает со страницы список постов, которые советует Дискорд."""
        if isinstance(raw_data, binary):
            raw_data = raw_data.decode("utf-8", "replace")
        elif not isinstance(raw_data, text):
            raw_data = text(raw_data)

        section = raw_data.find('<section class="block block-type-stream">')
        if section < 0:
            return []
        section2 = raw_data.find('<section class="block block-type-stream">', section + 1)
        if section2 < raw_data.find('Дискорд советует', section):
            section = section2
        del section2

        section = raw_data[section:raw_data.find('</section>', section + 1) + 10]
        section = utils.replace_cloudflare_emails(section)
        section = utils.parse_html_fragment(section)
        if not section:
            return []
        section = section[0]

        posts = []
        for li in section.xpath('div[@class="block-content"]/ul/li'):
            posts.append(parse_discord(li))

        return posts

    def get_posts(self, url="/index/newall/", raw_data=None):
        """Возвращает список постов со страницы или RSS. Если постов нет - кидает исключение TabunError("No post")."""
        if not raw_data:
            req = self.urlopen(url)
            url = req.url
            raw_data = req.read()
        raw_data = utils.replace_cloudflare_emails(raw_data)

        posts = []

        f = raw_data.find(b"<rss")
        if f < 250 and f >= 0:
            node = utils.lxml.etree.fromstring(raw_data)  # pylint: disable=no-member
            channel = node.find("channel")
            if channel is None:
                raise TabunError("No RSS channel")
            items = channel.findall("item")
            items.reverse()

            # TODO: заюзать новое экранирование
            for item in items:
                post = parse_rss_post(item)
                if post:
                    posts.append(post)

            return posts

        data = utils.find_substring(raw_data, b"<article ", b"</article> <!-- /.topic -->", extend=True)
        if not data:
            raise TabunError("No post")

        can_be_short = not url.split('?', 1)[0].endswith('.html')
        escaped_data = utils.escape_comment_contents(utils.escape_topic_contents(data, can_be_short))
        # items = filter(lambda x: not isinstance(x, text_types) and x.tag == "article", utils.parse_html_fragment(escaped_data))
        items = [x for x in utils.parse_html_fragment(escaped_data) if not isinstance(x, text_types) and x.tag == "article"]
        items.reverse()

        for item in items:
            post = parse_post(item)
            if post:
                posts.append(post)

        return posts

    def get_post(self, post_id, blog=None, raw_data=None):
        """Возвращает пост по номеру. Рекомендуется указать url-имя блога, чтобы избежать перенаправления и лишнего запроса.
        Если поста нет - кидается исключением TabunError("No post"). В случае проблем с парсингом может вернуть None.
        """
        if blog:
            url = "/blog/" + text(blog) + "/" + text(post_id) + ".html"
        else:
            url = "/blog/" + text(post_id) + ".html"

        if not raw_data:
            req = self.urlopen(url)
            url = req.url
            raw_data = req.read()
        raw_data = utils.replace_cloudflare_emails(raw_data)

        posts = self.get_posts(url, raw_data=raw_data)
        if not posts:
            return

        post = posts[0]

        comments_count = utils.find_substring(raw_data, b'<div class="comments" id="comments"', b'</h3>')
        if comments_count:
            comments_count = utils.find_substring(raw_data, b'<span id="count-comments">', b'</span>', with_start=False, with_end=False)
            post.comments_count = int(comments_count.strip())
            post.comments_new_count = 0
        return post

    def get_comments(self, url="/comments/", raw_data=None):
        """Возвращает словарь id-комментарий."""
        if not raw_data:
            req = self.urlopen(url)
            url = req.url
            raw_data = req.read()
            del req
        blog, post_id = parse_post_url(url)

        raw_data = utils.find_substring(raw_data, b'<div class="comments', b'<!-- /content -->', extend=True, with_end=False)
        if not raw_data:
            return {}
        raw_data = utils.replace_cloudflare_emails(raw_data)
        escaped_data = utils.escape_comment_contents(utils.escape_topic_contents(raw_data, True))
        div = utils.parse_html_fragment(escaped_data)
        if not div:
            return {}
        div = div[0]

        raw_comms = []

        for node in div.findall("div"):
            if node.get('class') == 'comment-wrapper':
                raw_comms.extend(parse_wrapper(node))

        # for /comments/ page
        for sect in div.findall("section"):
            if "comment" in sect.get('class', ''):
                raw_comms.append(sect)

        comms = {}

        for sect in raw_comms:
            c = parse_comment(sect, post_id, blog)
            if c:
                comms[c.comment_id] = c
            else:
                if sect.get("id", "").find("comment_id_") == 0:
                    c = parse_deleted_comment(sect, post_id, blog)
                    if c:
                        comms[c.comment_id] = c
                    else:
                        print("Warning: cannot parse deleted comment %s" % sect.get("id"))
                else:
                    print("Warning: unknown comment format %s" % sect.get("id"))

        return comms

    def get_blogs_list(self, page=1, order_by="blog_rating", order_way="desc", url=None):
        """Возвращает список объектов Blog."""
        if not url:
            url = "/blogs/" + (("page" + text(page) + "/") if page > 1 else "")
            url += "?order=" + text(order_by)
            url += "&order_way=" + text(order_way)

        data = self.urlopen(url).read()
        data = utils.find_substring(data, b'<table class="table table-blogs', b'</table>')
        node = utils.parse_html_fragment(data)
        if not node:
            return []
        node = node[0]
        if node.find("tbody") is not None:
            node = node.find("tbody")

        blogs = []

        for tr in node.findall("tr"):
            p = tr.xpath('td[@class="cell-name"]/p')
            if len(p) == 0:
                continue
            p = p[0]
            a = p.find("a")

            link = a.get('href')
            if not link:
                continue

            blog = link[:link.rfind('/')]
            blog = blog[blog.rfind('/') + 1:]

            name = text(a.text)
            closed = bool(p.xpath('i[@class="icon-synio-topic-private"]'))

            cell_readers = tr.xpath('td[@class="cell-readers"]')[0]
            readers = int(cell_readers.text)
            blog_id = int(cell_readers.get('id').rsplit("_", 1)[-1])
            rating = float(tr.findall("td")[-1].text)

            creator = tr.xpath('td[@class="cell-name"]/span[@class="user-avatar"]/a')[-1].text

            blogs.append(Blog(blog_id, blog, name, creator, readers, rating, closed))

        return blogs

    def get_blog(self, blog, raw_data=None):
        """Возвращает информацию о блоге. Функция не доделана."""
        blog = text(blog)
        if not raw_data:
            req = self.urlopen("/blog/" + text(blog) + "/")
            raw_data = req.read()
            del req
        data = utils.find_substring(raw_data, b'<div class="blog-top">', b'<div class="nav-menu-wrapper">', with_end=False)
        data = utils.replace_cloudflare_emails(data)

        node = utils.parse_html_fragment(b'<div>' + data + b'</div>')
        if not node:
            return

        blog_top = node[0].xpath('div[@class="blog-top"]')[0]
        blog_inner = node[0].xpath('div[@id="blog"]/div[@class="blog-inner"]')[0]
        blog_footer = node[0].xpath('div[@id="blog"]/footer[@class="blog-footer"]')[0]

        name = blog_top.xpath('h2/text()[1]')[0].rstrip()
        closed = len(blog_top.xpath('h2/i[@class="icon-synio-topic-private"]')) > 0

        vote_item = blog_top.xpath('div/div[@class="vote-item vote-count"]')[0]
        vote_count = int(vote_item.get("title", "0").rsplit(" ", 1)[-1])
        blog_id = int(vote_item.find("span").get("id").rsplit("_", 1)[-1])
        vote_total = vote_item.find("span").text
        if vote_total[0] == "+":
            vote_total = float(vote_total[1:])
        else:
            vote_total = float(vote_total)

        avatar = blog_inner.xpath("header/img")[0].get("src")

        content = blog_inner.find("div")
        info = content.find("ul")

        description = content.find("div")
        created = time.strptime(utils.mon2num(info.xpath('li[1]/strong/text()')[0]), "%d %m %Y")
        posts_count = int(info.xpath('li[2]/strong/text()')[0])
        readers = int(info.xpath('li[3]/strong/text()')[0])
        admins = []
        moderators = []

        arr = admins
        for user in content.xpath('span[@class="user-avatar"]'):
            t = user.getprevious().getprevious().text
            if t and "Модераторы" in t:
                arr = moderators
            arr.append(user.text_content().strip())

        creator = blog_footer.xpath("div/a[2]/text()[1]")[0]

        return Blog(blog_id, blog, name, creator, readers, vote_total, closed, description, admins, moderators, vote_count, posts_count, created)

    def get_post_and_comments(self, post_id, blog=None, raw_data=None):
        """Возвращает пост и список комментов. По сути просто вызывает функции get_posts и get_comments."""
        post_id = int(post_id)
        if not raw_data:
            req = self.urlopen("/blog/" + (text(blog) + "/" if blog else "") + text(post_id) + ".html")
            url = req.url
            raw_data = req.read()
            del req

        post = self.get_posts(url=url, raw_data=raw_data)
        comments = self.get_comments(url=url, raw_data=raw_data)

        return (post[0] if post else None), comments

    def get_comments_from(self, post_id, comment_id=0, typ="blog"):
        """Возвращает комментарии к посту, начиная с определённого номера комментария. На сайте используется для подгрузки новых комментариев.
        Тип - blog (пост) или talk (личные сообщения).
        """
        post_id = int(post_id)
        comment_id = int(comment_id) if comment_id else 0

        url = "/" + (typ if typ in ("blog", "talk") else "blog") + "/ajaxresponsecomment/"

        try:
            data = self.ajax(url, {'idCommentLast': comment_id, 'idTarget': post_id, 'typeTarget': 'topic'})
        except TabunResultError as exc:
            if exc.data and exc.data.get('sMsg') in (
                "Истекло время для редактирование комментариев",
                "Не хватает прав для редактирования коментариев",
                "Запрещено редактировать, коментарии с ответами"
            ):
                data = exc.data
            else:
                raise

        comms = {}
        for comm in data['aComments']:
            node = utils.parse_html_fragment(utils.escape_comment_contents(comm['html'].encode('utf-8')))
            pcomm = parse_comment(node[0], post_id, None, comm['idParent'])
            if pcomm:
                comms[pcomm.comment_id] = pcomm
            else:
                print("Warning: cannot parse ajax comment from %s" % post_id)

        return comms

    def get_stream_comments(self):
        """Возвращает «Прямой эфир» - объекты StreamItem."""
        self.check_login()
        data = self.urlopen(
            "/ajax/stream/comment/",
            "security_ls_key=" + urequest.quote(self.security_ls_key)
        ).read()

        data = self.jd.decode(data.decode('utf-8', 'replace'))
        if data['bStateError']:
            raise TabunResultError(data['sMsg'])

        node = utils.parse_html_fragment(data['sText'])
        if not node:
            return []
        node = node[0]

        items = []

        for item in node.findall("li"):
            p = item.find("p")
            a, blog_a = p.findall("a")[:2]

            author = a.text_content()
            if blog_a.get('href', '').endswith('/created/topics/'):
                blog = None
            else:
                blog = blog_a.get('href', '')[:-1].rsplit("/", 1)[-1]
            blog_title = blog_a.text_content()

            comment_id = int(item.find("a").get('href', '').rsplit("/", 1)[-1])
            title = item.find("a").text_content()

            comments_count = int(item.find("span").text_content())

            sitem = StreamItem(blog, blog_title, title, author, comment_id, comments_count)
            items.append(sitem)

        return items

    def get_stream_topics(self):
        """Возвращает список последних постов (без самого содержимого постов, только автор, дата, заголовки и число комментариев)."""
        data = self.ajax('/ajax/stream/topic/')
        node = utils.parse_html_fragment(data['sText'])
        if not node:
            return []
        node = node[0]

        items = []

        for item in node.findall("li"):
            p = item.find("p")
            a = p.find("a")
            topic_a = item.findall("a")[1]

            author = a.text_content()
            title = topic_a.text_content().strip()
            blog, post_id = parse_post_url(topic_a.get('href', ''))
            comments_count = int(item.find("span").text_content())

            items.append(Post(
                time=None, blog=blog, post_id=post_id, author=author, title=title, draft=False,
                vote_count=None, vote_total=None, body=None, tags=[], comments_count=comments_count
            ))

        return items

    def get_short_blogs_list(self, raw_data=None):
        """Возвращает пустой список. После обновления Табуна не работает, функция оставлена для обратной совместимости.
        """
        return []

    def get_people_list(self, page=1, order_by="user_rating", order_way="desc", url=None):
        """Возвращает список броняш - объекты UserInfo."""
        if not url:
            url = "/people/" + ("index/page" + text(page) + "/" if page > 1 else "")
            url += "?order=" + text(order_by)
            url += "&order_way=" + text(order_way)

        data = self.urlopen(url).read()
        data = utils.find_substring(data, b'<table class="table table-users', b'</table>')
        if not data:
            return []
        node = utils.parse_html_fragment(data)
        if not node:
            return []
        node = node[0]
        if node.find("tbody") is not None:
            node = node.find("tbody")

        peoples = []

        for tr in node.findall("tr"):
            username = tr.xpath('td[@class="cell-name"]/div/p[1]/a/text()[1]')
            if not username:
                continue

            realname = tr.xpath('td[@class="cell-name"]/div/p[2]/text()[1]')
            if not realname:
                realname = None
            else:
                realname = text(realname[0])

            skill = tr.xpath('td[@class="cell-skill"]/text()[1]')
            if not skill:
                continue

            rating = tr.xpath('td[@class="cell-rating "]/strong/text()[1]')
            if not rating:
                rating = tr.xpath('td[@class="cell-rating negative"]/strong/text()[1]')
            if not rating:
                continue

            userpic = tr.xpath('td[@class="cell-name"]/a/img/@src')
            if not userpic:
                continue

            peoples.append(UserInfo(utils.parse_avatar_url(userpic[0])[0] or -1, username[0], realname, skill[0], rating[0], userpic=userpic[0]))

        return peoples

    def get_profile(self, username=None, raw_data=None):
        if not raw_data:
            raw_data = self.urlopen("/profile/" + urequest.quote(text(username).encode('utf-8'))).read()

        data = utils.find_substring(raw_data, b'<div id="content"', b'<!-- /content ', extend=True, with_end=False)
        if not data:
            return
        data = utils.replace_cloudflare_emails(data)
        node = utils.parse_html_fragment(data)
        if not node:
            return
        node = node[0]

        profile = node.xpath('div[@class="profile"]')[0]

        username = profile.xpath('h2[@itemprop="nickname"]/text()')[0]
        realname = profile.xpath('p[@class="user-name"]/text()')

        skill = float(profile.xpath('div[@class="strength"]/div[1]/text()')[0])
        rating = profile.xpath('div[@class="vote-profile"]/div[1]')[0]
        user_id = int(rating.get("id").rsplit("_")[-1])
        rating = float(rating.findall('div')[1].find('span').text.strip().replace('+', ''))

        userpic = node.xpath('div[@class="profile-info-about"]/a[1]/img')[0].get('src')

        birthday = None
        registered = None
        last_activity = None
        gender = None

        uls = node.xpath('div[@class="wrapper"]/div[@class="profile-left"]/ul[@class="profile-dotted-list"]/li')

        blogs = {
            'owner': [],
            'admin': [],
            'moderator': [],
            'member': []
        }

        for ul in uls:
            name = ul.find('span').text.strip()
            value = ul.find('strong')
            if name == 'Дата рождения:':
                birthday = time.strptime(utils.mon2num(value.text), '%d %m %Y')
            elif name == 'Зарегистрирован:':
                try:
                    registered = time.strptime(utils.mon2num(value.text), '%d %m %Y, %H:%M')
                except ValueError:
                    if username != 'guest':
                        raise
            elif name == 'Последний визит:':
                last_activity = time.strptime(utils.mon2num(value.text), '%d %m %Y, %H:%M')
            elif name == 'Пол:':
                gender = 'M' if value.text.strip() == 'мужской' else 'F'

            elif name in ('Создал:', 'Администрирует:', 'Модерирует:', 'Состоит в:'):
                blist = []
                for b in value.findall('a'):
                    link = b.get('href', '')[:-1]
                    if link:
                        blist.append((link[link.rfind('/') + 1:], b.text_content()))

                if name == 'Создал:':
                    blogs['owner'] = blist
                elif name == 'Администрирует:':
                    blogs['admin'] = blist
                elif name == 'Модерирует:':
                    blogs['moderator'] = blist
                elif name == 'Состоит в:':
                    blogs['member'] = blist

        description = node.xpath('div[@class="profile-info-about"]/div[@class="text"]')

        if registered is None:
            # забагованная учётка Tailsik208 со смайликом >_< (была когда-то)
            registered = time.gmtime(0)
            description = []

        foto = raw_data.find(b'id="foto-img"')
        if foto >= 0:
            foto = raw_data[raw_data.rfind(b'<img', 0, foto):]
            foto = foto[:foto.find(b'</a>')]
        else:
            foto = None

        if foto is not None:
            foto = utils.parse_html_fragment(foto)
            foto = foto[0].get('src') if foto else None
            if foto.endswith('user_photo_male.png') or foto.endswith('user_photo_female.png'):
                foto = None

        return UserInfo(user_id, username, realname[0] if realname else None, skill, rating, userpic, foto, gender, birthday, registered, last_activity, description[0] if description else None, blogs)

    def poll_answer(self, post_id, answer=-1):
        """Проголосовать в опросе. -1 - воздержаться. Возвращает новый объект Poll."""
        if answer < -1:
            answer = -1
        if post_id < 0:
            post_id = 0

        fields = {
            "idTopic": post_id,
            "idAnswer": answer
        }

        data = self.ajax('/ajax/vote/question/', fields)
        poll = utils.parse_html_fragment('<div id="topic_question_area_' + text(post_id) + '" class="poll">' + data['sText'] + '</div>')
        return parse_poll(poll[0])

    def vote(self, post_id, value=0):
        """Ставит плюсик (1) или минусик (-1) или ничего (0) посту и возвращает его рейтинг."""
        fields = {
            "idTopic": int(post_id),
            "value": int(value)
        }

        return int(self.ajax('/ajax/vote/topic/', fields)['iRating'])

    def vote_comment(self, comment_id, value):
        """Ставит плюсик (1) или минусик (-1) комменту и возвращает его рейтинг."""
        fields = {
            "idComment": int(comment_id),
            "value": int(value)
        }

        return int(self.ajax('/ajax/vote/comment/', fields)['iRating'])

    def vote_user(self, user_id, value):
        """Ставит плюсик (1) или минусик (-1) пользователю и возвращает его рейтинг."""
        fields = {
            "idUser": int(user_id),
            "value": int(value)
        }

        return float(self.ajax('/ajax/vote/user/', fields)['iRating'])

    def vote_blog(self, blog_id, value):
        """Ставит плюсик (1) или минусик (-1) блогу и возвращает его рейтинг."""
        fields = {
            "idBlog": int(blog_id),
            "value": int(value)
        }

        return float(self.ajax('/ajax/vote/blog/', fields)['iRating'])

    def favourite_topic(self, post_id, type=True):
        """Добавляет (type=True) пост в избранное или убирает (type=False) оттуда. Возвращает новое число пользователей, добавивших пост в избранное."""
        fields = {
            "idTopic": int(post_id),
            "type": "1" if type else "0"
        }

        return self.ajax('/ajax/favourite/topic/', fields)['iCount']

    def favourite_comment(self, comment_id, type=True):
        """Добавляет (type=True) коммент в избранное или убирает (type=False) оттуда. Возвращает новое число пользователей, добавивших коммент в избранное."""
        fields = {
            "idComment": int(comment_id),
            "type": "1" if type else "0"
        }

        return self.ajax('/ajax/favourite/comment/', fields)['iCount']

    def edit_comment(self, comment_id, text):
        """Редактирует комментарий и возвращает новое тело комментария."""
        fields = {
            "commentId": int(comment_id),
            "text": text.encode("utf-8")
        }

        data = self.ajax('/role_ajax/savecomment/', fields)
        # TODO: raw_body
        return utils.parse_html_fragment('<div class="text">' + data['sText'] + '</div>')[0]

    def get_editable_post(self, post_id, raw_data=None):
        """Возвращает blog_id, заголовок, исходный код поста, список тегов и галочку закрытия комментариев (True/False)."""
        if not raw_data:
            req = self.urlopen("/topic/edit/" + text(int(post_id)) + "/")
            raw_data = req.read()
            del req

        raw_data = utils.find_substring(
            raw_data,
            b'<form action="" method="POST" enctype="multipart/form-data" id="form-topic-add"',
            b'<div class="topic-preview"',
            extend=True, with_end=False
        )

        raw_data = utils.replace_cloudflare_emails(raw_data)
        form = utils.parse_html_fragment(raw_data)
        if len(form) == 0:
            return None
        form = form[0]

        blog_id = form.xpath('p/select[@id="blog_id"]')[0]
        ok = False
        for x in blog_id.findall("option"):
            if x.get("selected") is not None:
                ok = True
                blog_id = int(x.get("value"))
                break
        if not ok:
            blog_id = 0

        title = form.xpath('p/input[@id="topic_title"]')[0].get("value", "")
        body = form.xpath("textarea")[0].text
        tags = form.xpath('p/input[@id="topic_tags"]')[0].get("value", "").split(",")
        forbid_comment = bool(form.xpath('p/label/input[@id="topic_forbid_comment"]')[0].get("checked"))
        return blog_id, title, body, tags, forbid_comment

    def get_editable_blog(self, blog_id, raw_data=None):
        """Возвращает заголовок блога, URL, тип (True - закрытый, False - открытый), описание и ограничение рейтинга."""
        if not raw_data:
            req = self.urlopen("/blog/edit/" + text(int(blog_id)) + "/")
            raw_data = req.read()
            del req

        raw_data = utils.find_substring(
            raw_data,
            b'<form method="post" enctype="multipart/form-data" class="wrapper-content">',
            b'</form>'
        )

        if not raw_data:
            return
        raw_data = utils.replace_cloudflare_emails(raw_data)
        form = utils.parse_html_fragment(raw_data)
        if not form:
            return
        form = form[0]

        blog_title = form.xpath('p/input[@id="blog_title"]')[0].get('value')
        blog_url = form.xpath('p/input[@id="blog_url"]')[0].get('value')
        blog_type = form.xpath('p/select[@id="blog_type"]/option[@selected]')[0].get('value')
        blog_description = form.xpath('p/textarea[@id="blog_description"]/text()[1]')[0].replace('\r\n', '\n')
        blog_limit_rating_topic = float(form.xpath('p/input[@id="blog_limit_rating_topic"]')[0].get('value'))

        return blog_title, blog_url, blog_type == "close", blog_description, blog_limit_rating_topic

    def edit_post(self, post_id, blog_id, title, body, tags, draft=False):
        """Редактирует пост и возвращает его блог и номер в случае удачи или (None,None) в случае неудачи."""
        self.check_login()
        blog_id = int(blog_id if blog_id else 0)

        if isinstance(tags, (tuple, list)):
            tags = ", ".join(tags)

        fields = {
            'topic_type': 'topic',
            'security_ls_key': self.security_ls_key,
            'blog_id': text(blog_id),
            'topic_title': text(title),
            'topic_text': text(body),
            'topic_tags': text(tags)
        }
        if draft:
            fields['submit_topic_save'] = "Сохранить в черновиках"
        else:
            fields['submit_topic_publish'] = "Опубликовать"

        link = self.send_form('/topic/edit/' + text(int(post_id)) + '/', fields, redir=False).headers.get('location')
        return parse_post_url(link)

    def invite(self, blog_id, username):
        """Отправляет инвайт в блог с указанным номером указанному пользователю (или пользователям, если указать несколько через запятую).
        Возвращает словарь, который содержит пары юзернейм-текст ошибки в случае, если кому-то инвайт не отправился. Если всё хорошо, то словарь пустой.
        """
        self.check_login()

        fields = {
            "users": text(username),
            "idBlog": text(int(blog_id) if blog_id else 0),
            'security_ls_key': self.security_ls_key,
        }

        data = self.send_form("/blog/ajaxaddbloginvite/", fields).read()
        result = self.jd.decode(data.decode('utf-8'))
        if result['bStateError']:
            raise TabunResultError(result['sMsg'])

        users = {}
        for x in result['aUsers']:
            if x['bStateError']:
                users[x['sUserLogin']] = x['sMsg']

        return users

    def add_talk(self, talk_users, title, body):
        """Отправляет новое личное сообщение пользователям. Возвращает id созданой беседы."""
        if isinstance(talk_users, text_types):
            talk_users = [text(x.strip()) for x in talk_users.split(',')]

        fields = {
            'security_ls_key': self.security_ls_key,
            'talk_users': ', '.join(talk_users),
            'talk_title': text(title),
            'talk_text': text(body),
            'submit_talk_add': 'Отправить'
        }

        result = self.send_form('/talk/add/', fields, redir=False)
        data = result.read()
        errors = utils.find_substring(data, b'<ul class="system-message-error">', b'</ul>')
        if errors and ':' in errors:
            errors = utils.parse_html_fragment(errors)[0]
            errors = '; '.join(x.text_content().split('Ошибка:', 1)[-1].strip() for x in errors.findall('li'))
            raise TabunResultError(errors)

        link = result.headers.get('location')
        if '/talk/read/' in link:
            return int(link.rstrip('/').rsplit('/', 1)[-1])

    def get_talk_list(self, page=1, raw_data=None):
        """Возвращает список объектов Talk с личными сообщениями."""
        self.check_login()
        if not raw_data:
            req = self.urlopen("/talk/inbox/page{}/".format(int(page)))
            raw_data = req.read()
            del req

        raw_data = utils.find_substring(raw_data, b'<table ', b'</table>')
        if not raw_data:
            return []

        raw_data = utils.replace_cloudflare_emails(raw_data)
        node = utils.parse_html_fragment(raw_data)[0]

        elems = []

        for elem in node.xpath('//tr')[1:]:
            elem = parse_talk_item(elem)
            if elem:
                elems.append(elem)

        return elems

    def get_talk(self, talk_id, raw_data=None):
        """Возвращает объект Talk беседы с переданным номером."""
        self.check_login()
        if not raw_data:
            req = self.urlopen("/talk/read/" + text(int(talk_id)) + "/")
            raw_data = req.read()
            del req

        data = utils.find_substring(raw_data, b"<article ", b"</article>", extend=True)
        if not data:
            return

        data = utils.replace_cloudflare_emails(data)
        item = utils.parse_html_fragment(data)[0]
        title = item.find("header").find("h1").text
        body = item.xpath('div[@class="topic-content text"]')
        if len(body) == 0:
            return
        body = body[0]

        recipients = map(lambda x: x.text.strip(), item.xpath('div[@class="talk-search talk-recipients"]/header/a[@class!="link-dotted"]'))

        footer = item.find("footer")
        author = footer.xpath('ul/li[@class="topic-info-author"]/a[2]/text()')[0].strip()
        date = footer.xpath('ul/li[@class="topic-info-date"]/time')[0]
        date = time.strptime(date.get("datetime")[:-6], "%Y-%m-%dT%H:%M:%S")

        comments = self.get_comments(raw_data=raw_data)

        return TalkItem(talk_id, recipients, False, title, date, body, author, comments)

    def get_activity(self, url='/stream/all/', raw_data=None):
        """Возвращает список последних событий."""
        if not raw_data:
            req = self.urlopen(url)
            raw_data = req.read()
            del req

        raw_data = utils.find_substring(raw_data, b'<ul class="stream-list', b'<!-- /content', with_end=False)
        if not raw_data:
            return []
        raw_data = utils.replace_cloudflare_emails(raw_data)
        node = utils.parse_html_fragment(raw_data[:raw_data.rfind(b'</ul>')])
        if not node:
            return []
        node = node[0]

        inp = b'<input type="hidden" id="stream_last_id" value="'
        if raw_data.rfind(inp) > 0:
            last_id = raw_data[raw_data.rfind(inp) + len(inp):]
            last_id = int(last_id[:last_id.find(b'"')])
        else:
            last_id = -1

        items = []

        for li in node.findall('li'):
            if not li.get('class', '').startswith('stream-item'):
                continue
            item = parse_activity(li)
            if item:
                items.append(item)

        if item:
            item.id = last_id
        return last_id, items

    def get_more_activity(self, last_id=0x7fffffff):
        """Возвращает список событий старее данного id."""
        self.check_login()

        fields = {
            "last_id": text(int(last_id)),
            'security_ls_key': self.security_ls_key,
        }

        data = self.send_form("/stream/get_more_all/", fields).read()
        result = self.jd.decode(data.decode('utf-8'))
        if result['bStateError']:
            raise TabunResultError(result['sMsg'])

        items = []

        last_id = int(result.get('iStreamLastId', 0))
        item = None
        for li in utils.parse_html_fragment(result['result']):
            if li.tag != 'li' or not li.get('class', '').startswith('stream-item'):
                continue
            item = parse_activity(li)
            if item:
                items.append(item)

        if item:
            item.id = last_id
        return last_id, items


def parse_activity(item):
    classes = item.get('class').split()

    post_id = None
    comment_id = None
    blog = None
    title = None
    data = None
    date = None

    if 'stream-item-type-add_topic' in classes:
        typ = ActivityItem.POST_ADD
        href = item.xpath('a[2]')[0].get('href')
        blog, post_id = parse_post_url(href)
        title = item.xpath('a[2]/text()[1]')[0]

    elif 'stream-item-type-add_comment' in classes:
        typ = ActivityItem.COMMENT_ADD
        href = item.xpath('a[2]')[0].get('href')
        blog, post_id = parse_post_url(href)
        comment_id = int(href[href.rfind("#comment") + 8:])
        data = item.xpath('div/text()')
        data = data[0] if data else None
        title = item.xpath('a[2]/text()[1]')[0]

    elif 'stream-item-type-add_blog' in classes:
        typ = ActivityItem.BLOG_ADD
        href = item.xpath('a[2]')[0].get('href')[:-1]
        blog = href[href.rfind('/') + 1:]
        title = item.xpath('a[2]/text()[1]')[0]

    elif 'stream-item-type-vote_topic' in classes:
        typ = ActivityItem.POST_VOTE
        href = item.xpath('a[2]')[0].get('href')
        blog, post_id = parse_post_url(href)
        title = item.xpath('a[2]/text()[1]')[0]

    elif 'stream-item-type-vote_comment' in classes:
        typ = ActivityItem.COMMENT_VOTE
        href = item.xpath('a[2]')[0].get('href')
        blog, post_id = parse_post_url(href)
        comment_id = int(href[href.rfind("#comment") + 8:])
        title = item.xpath('a[2]/text()[1]')[0]

    elif 'stream-item-type-vote_blog' in classes:
        typ = ActivityItem.BLOG_VOTE
        href = item.xpath('a[2]')[0].get('href')[:-1]
        blog = href[href.rfind('/') + 1:]
        title = item.xpath('a[2]/text()[1]')[0]

    elif 'stream-item-type-vote_user' in classes:
        typ = ActivityItem.USER_VOTE
        data = item.xpath('span/a[2]/text()')[0]

    elif 'stream-item-type-add_friend' in classes:
        typ = ActivityItem.FRIEND_ADD
        data = item.xpath('span/a[2]/text()')[0]

    elif 'stream-item-type-join_blog' in classes:
        typ = ActivityItem.JOIN_BLOG
        href = item.xpath('a[2]')[0].get('href')[:-1]
        blog = href[href.rfind('/') + 1:]
        title = item.xpath('a[2]/text()[1]')[0]

    else:
        return

    username = item.xpath('p[@class="info"]/a/strong/text()[1]')[0]
    date = item.xpath('p[@class="info"]/span[@class="date"]')[0].get('title')
    if not date:
        return
    date = time.strptime(utils.mon2num(date), "%d %m %Y, %H:%M")
    return ActivityItem(typ, date, post_id, comment_id, blog, username, title, data)


def parse_post(item):
    # Парсинг поста. Не надо юзать эту функцию.
    header = item.find("header")
    title = header.find("h1")
    if title is None:
        return

    link = title.find("a")
    if link is not None:
        # есть ссылка на сам пост, парсим её
        blog, post_id = parse_post_url(link.get("href"))
    else:
        # если ссылки нет, то костыляем: достаём блог из ссылки на него
        blog = None
        link = header.xpath('div/a[@class="topic-blog"]')
        if not link:
            link = header.xpath('div/a[@class="topic-blog private-blog"]')
        if link:
            link = link[0].get('href')
            if link and '/blog/' in link:
                blog = link[:-1]
                blog = blog[blog.rfind('/', 1) + 1:]
        else:
            raise ValueError('Cannot get blog from post "%s"' % title.text_content())

        # достаём номер поста из блока с рейтингом
        vote_elem = header.xpath('div/div[@class="topic-info-vote"]/div')
        if vote_elem and vote_elem[0].get('id'):
            post_id = int(vote_elem[0].get('id').rsplit('_', 1)[-1])
        else:
            post_id = -1
        del vote_elem
    del link

    author = header.xpath('div/a[@rel="author"]/text()[1]')
    if len(author) == 0:
        return
    author = author[0]

    title = title.text_content().strip()
    private = bool(header.xpath('div/a[@class="topic-blog private-blog"]'))

    blog_name = header.xpath('div/a[@class="topic-blog"]/text()[1]')
    if not blog_name:
        blog_name = header.xpath('div/a[@class="topic-blog private-blog"]/text()[1]')
    if len(blog_name) > 0:
        blog_name = text(blog_name[0])
    else:
        blog_name = None

    post_time = item.xpath('footer/ul/li[1]/time')
    if not post_time:
        post_time = item.xpath('header/div[@class="topic-info"]/time')  # mylittlebrony.ru
    if post_time:
        post_time = time.strptime(post_time[0].get("datetime")[:-6], "%Y-%m-%dT%H:%M:%S")
    else:
        post_time = time.localtime()

    body = item.xpath('div[@class="topic-content text"]')
    if len(body) == 0:
        return
    body = body[0]

    if body.get('data-escaped') == '1':
        # всё почищено в utils
        raw_body = body.text
        is_short = body.get('data-short') == '1'
        # TODO: cut_text

    else:
        raw_body = None

        # чистим от topic-actions, а также сносим мусорные отступы
        post_header = body.xpath('header[@class="topic-header"]')
        if post_header:
            post_header = post_header[0]
            body.remove(post_header)
            body.text = ''
            if post_header.tail:
                body.text = post_header.tail.lstrip()
        else:
            post_header = None
            if body.text:
                body.text = body.text.lstrip()
        body.tail = ""

        nextbtn = body.xpath('a[@title="Читать дальше"][1]')
        is_short = len(nextbtn) > 0
        if is_short:
            body.remove(nextbtn[-1])

        if len(body) > 0 and body[-1].tail:
            body[-1].tail = body[-1].tail.rstrip()
        elif len(body) == 0 and body.text:
            body.text = body.text.rstrip()

    footer = item.find("footer")
    ntags = footer.find("p")
    tags = []
    if ntags is not None:
        for ntag in ntags.findall("a"):
            if not ntag.text:
                continue
            tags.append(text(ntag.text))

    draft = bool(header.xpath('h1/i[@class="icon-synio-topic-draft"]'))

    rateelem = header.xpath('div[@class="topic-info"]/div[@class="topic-info-vote"]/div/div[@class="vote-item vote-count"]')
    if rateelem:
        rateelem = rateelem[0]

        vote_count = int(rateelem.get("title").rsplit(" ", 1)[-1])
        vote_total = rateelem.getchildren()[0]
        if not vote_total.getchildren():
            vote_total = int(vote_total.text.replace("+", ""))
        else:
            vote_total = None
    else:
        vote_count = -1
        vote_total = 0

    poll = item.xpath('div[@class="poll"]')
    if poll:
        poll = parse_poll(poll[0])

    fav = footer.xpath('ul[@class="topic-info"]/li[starts-with(@class, "topic-info-favourite")]')[0]
    favourited = fav.get('class').endswith(' active')
    if not favourited:
        i = fav.find('i')
        favourited = i is not None and i.get('class', '').endswith(' active')
    favourite = fav.xpath('span[@class="favourite-count"]/text()')
    try:
        favourite = int(favourite[0]) if favourite and favourite[0] else 0
    except ValueError:
        favourite = 0

    comments_count = None
    comments_new_count = None
    download_count = None
    for li in footer.xpath('ul[@class="topic-info"]/li[@class="topic-info-comments"]'):
        a = li.find('a')
        if a is None:
            continue
        icon = a.find('i')
        if icon is None:
            continue
        if icon.get('class') in ('icon-synio-comments-green-filled', 'icon-synio-comments-blue'):
            span = a.findall('span')
            comments_count = int(span[0].text.strip())
            if len(span) > 1:
                comments_new_count = int(span[1].text.strip()[1:])
            else:
                comments_new_count = 0
        elif icon.get('class') == 'icon-download-alt':
            download_count = int(a.find('span').text.strip())

    download = None
    if download_count is not None:
        dname = None
        dsize = None

        dlink = item.xpath('div[@class="download"]')
        if dlink:
            dlink = dlink[0].find('a')
        else:
            dlink = None

        if dlink is not None and dlink.get('href'):
            m = post_file_regex.match(dlink.text.strip())
            dlink = dlink.get('href')
            if '/file/go/' in dlink and m:
                m = m.groups()
                dname = m[0]
                dsize = float(m[1])
                if m[3] == 'Кб':
                    dsize *= 1024
                elif m[3] == 'Мб':
                    dsize *= 1024 * 1024

        download = Download("file", post_id, dname, download_count, dsize)
        del dlink

    if not download:
        post_link = item.xpath('div[@class="topic-url"]/a')
        if post_link:
            link_count = int(post_link[0].get("title", "0").rsplit(" ", 1)[-1])
            post_link = post_link[0].text.strip()
            download = Download("link", post_id, post_link, link_count, None)

    return Post(
        post_time, blog, post_id, author, title, draft, vote_count, vote_total, body if raw_body is None else None, tags,
        comments_count, comments_new_count, is_short, private, blog_name,
        poll, favourite, favourited, download, raw_body
    )


def parse_poll(poll):
    # Парсинг опроса. Не надо юзать эту функцию.
    ul = poll.find('ul[@class="poll-result"]')
    if ul is not None:
        items = []
        for li in ul.findall('li'):
            item = [None, 0.0, 0]
            item[0] = li.xpath('dl/dd/text()[1]')[0].strip()
            item[1] = float(li.xpath('dl/dt/strong/text()[1]')[0][:-1])
            item[2] = int(li.xpath('dl/dt/span/text()[1]')[0][1:-1])
            items.append(item)
        poll_total = poll.xpath('div[@class="poll-total"]/text()')[-2:]
        total = int(poll_total[-2].rsplit(" ", 1)[-1])
        notvoted = int(poll_total[-1].rsplit(" ", 1)[-1])
        return Poll(total, notvoted, items)
    else:
        ul = poll.find('ul[@class="poll-vote"]')
        if ul is None:
            return
        items = []
        for li in ul.findall('li'):
            item = [None, -1.0, -1]
            item[0] = li.xpath('label/text()[1]')[0].strip()
            items.append(item)
        return Poll(-1, -1, items)


def parse_discord(li):
    body = '<div class="topic-content text">'
    body += li.get('title', '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    body += '</div>'
    body = utils.parse_html_fragment(body)[0]
    p = li.find('p')
    author = p.find('a').text.strip()
    tm = time.strptime(p.find('time').get('datetime')[:-6], "%Y-%m-%dT%H:%M:%S")
    blog_name, title = li.findall('a')[:2]
    blog_name = blog_name.text.strip()
    blog, post_id = parse_post_url(title.get('href'))
    title = title.text.strip()
    comments_count = int(li.find('span').text_content().strip())
    return Post(tm, blog, post_id, author, title, False, None, None, body, [], comments_count)


def parse_rss_post(item):
    # Парсинг rss. Не надо юзать эту функцию.
    link = text(item.find("link").text)

    title = text(item.find("title").text)
    if title is None:
        return

    author = item.find("dc:creator", {"dc": "http://purl.org/dc/elements/1.1/"})
    if author is None:
        return

    author = author.text

    if not author:
        return

    blog, post_id = parse_post_url(link)

    private = False  # в RSS закрытые блоги пока не обнаружены

    post_time = item.find("pubDate")
    if post_time is not None and post_time.text is not None:
        post_time = time.strptime(text(post_time.text).split(" ", 1)[-1][:-6], "%d %b %Y %H:%M:%S")
    else:
        post_time = time.localtime()

    node = item.find("description").text
    if not node:
        return
    node = utils.parse_html_fragment("<div class='topic-content text'>" + node + '</div>')[0]

    nextbtn = node.xpath('a[@title="Читать дальше"][1]')
    if len(nextbtn) > 0:
        node.remove(nextbtn[0])

    ntags = item.findall("category")
    if not ntags:
        return
    tags = []
    for ntag in ntags:
        if ntag.text:
            continue
        tags.append(text(ntag.text))

    return Post(post_time, blog, post_id, author, title, False, 0, 0, node, tags, short=len(nextbtn) > 0, private=private)


def parse_wrapper(node):
    # Парсинг коммента. Не надо юзать эту функцию.
    comms = []
    nodes = [node]
    while len(nodes) > 0:
        node = nodes.pop(0)
        sect = node.find("section")
        if not sect.get('class'):
            break
        if "comment" not in sect.get('class'):
            break
        comms.append(sect)
        nodes.extend(node.xpath('div[@class="comment-wrapper"]'))
    return comms


def parse_comment(node, post_id, blog=None, parent_id=None):
    # И это тоже парсинг коммента. Не надо юзать эту функцию.
    body = None
    try:
        info = node.xpath('ul[@class="comment-info"]')
        if len(info) == 0:
            info = node.xpath('div[@class="comment-path"]/ul[@class="comment-info"]')[0]
        else:
            info = info[0]

        comment_id = info.xpath('li[@class="comment-link"]/a')[0].get('href')
        if '#comment' in comment_id:
            comment_id = int(comment_id.rsplit('#comment', 1)[-1])
        else:
            comment_id = int(comment_id.rstrip('/').rsplit('/', 1)[-1])

        unread = "comment-new" in node.get("class", "")
        deleted = "comment-deleted" in node.get("class", "")

        # TODO: заюзать
        is_author = "comment-author" in node.get("class", "")
        is_self = "comment-self" in node.get("class", "")

        body = node.xpath('div[@class="comment-content"][1]/div')[0]
        raw_body = None
        if body is not None:
            if body.get('data-escaped') == '1':
                raw_body = body.text
            else:
                if body.text:
                    body.text = body.text.lstrip()
                body.tail = ""
                if len(body) > 0 and body[-1].tail:
                    body[-1].tail = body[-1].tail.rstrip()
                elif len(body) == 0 and body.text:
                    body.text = body.text.rstrip()

        nick = info.findall("li")[0].findall("a")[-1].text
        tm = info.findall("li")[1].find("time").get('datetime')
        tm = time.strptime(tm[:-6], "%Y-%m-%dT%H:%M:%S")

        post_title = None
        try:
            link = info.findall("li")
            if not link or link[-1].get('id'):
                link = info
            else:
                link = link[-1]
            link1 = link.xpath('a[@class="comment-path-topic"]')[0]
            post_title = link1.text
            link2 = link.xpath('a[@class="comment-path-comments"]')[0]
            link2 = link2.get('href')
            blog, post_id = parse_post_url(link2)
        except KeyboardInterrupt:
            raise
        except:
            pass

        if not parent_id:
            parent_id = info.xpath('li[@class="goto goto-comment-parent"]')
            if len(parent_id) > 0:
                parent_id = parent_id[0].find("a")
                if parent_id.get('onclick'):
                    parent_id = int(parent_id.get('onclick').rsplit(",", 1)[-1].split(")", 1)[0])
                elif '/comments/' in parent_id.get('href', ''):
                    parent_id = int(parent_id.get('href').rsplit('/', 1)[-1])
            else:
                parent_id = None

        vote = info.xpath('li[starts-with(@id, "vote_area_comment")]/span[@class="vote-count"]/text()[1]')
        if vote:
            vote = int(vote[0].replace("+", ""))
        else:
            vote = 0

        favourited = False
        favourite = info.xpath('li[@class="comment-favourite"]')
        if not favourite:
            favourite = None
        else:
            favourited = favourite[0].find('div')
            favourited = favourited is not None and 'active' in favourited.get('class', '')
            favourite = favourite[0].find('span').text
            try:
                favourite = int(favourite) if favourite else 0
            except:
                favourite = None

    except AttributeError:
        return
    except IndexError:
        return

    if body is not None:
        return Comment(tm, blog, post_id, comment_id, nick, body if raw_body is None else None, vote, parent_id,
                       post_title, unread, deleted, favourite, favourited, raw_body)


def parse_deleted_comment(node, post_id, blog=None):
    # И это тоже парсинг коммента! Но не простого, а удалённого.
    try:
        comment_id = int(node.get("id").rsplit("_", 1)[-1])
    except:
        return
    unread = "comment-new" in node.get("class", "")
    deleted = "comment-deleted" in node.get("class", "")
    if not deleted:
        print("Warning: deleted comment %d is not deleted! Please report to andreymal." % comment_id)
    body = None
    nick = None
    tm = None
    post_title = None
    vote = None
    parent_wrapper = node.getparent().getparent()
    if parent_wrapper is not None and parent_wrapper.tag == "div" and parent_wrapper.get("id", "").startswith("comment_wrapper_id_"):
        parent_id = int(parent_wrapper.get("id").rsplit("_", 1)[-1])
    else:
        parent_id = None
    return Comment(tm, blog, post_id, comment_id, nick, body, vote, parent_id, post_title, unread, deleted)


def parse_talk_item(node):
    checkbox, recs, title, date = node.findall("td")
    recipients = []
    for x in recs.findall("a"):
        recipients.append(x.text.strip())
    unread = bool(title.xpath('a/strong'))
    talk_id = title.find("a").get('href')[:-1]
    talk_id = int(talk_id[talk_id.rfind("/") + 1:])
    title = title.find("a").text_content()
    date = date.text.strip()
    date = time.strptime(utils.mon2num(date), '%d %m %Y')

    return TalkItem(talk_id, recipients, unread, title, date)


def parse_post_url(link):
    """Выдирает блог и номер поста из ссылки. Или возвращает (None, None), если выдрать не удалось."""
    if not link:
        return None, None
    m = post_url_regex.search(link)
    if not m:
        return None, None
    g = m.groups()
    return (g[1] if g[1] else None), int(g[2])
