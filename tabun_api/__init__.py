#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

import os
import re
import time
import logging
import warnings
import threading
from hashlib import md5
from datetime import datetime
from socket import timeout as socket_timeout
from json import JSONDecoder

from . import utils, compat
from .compat import PY2, BaseCookie, urequest, text_types, text, binary, html_unescape


__version__ = '0.7.1'

#: Адрес Табуна. Именно на указанный здесь адрес направляются запросы.
http_host = "https://tabun.everypony.ru"

#: Список полузакрытых блогов. В tabun_api нигде не используется, но может использоваться в использующих его программах.
halfclosed = ("borderline", "shipping", "erpg", "gak", "RPG", "roliplay", "tearsfromthemoon", "Technic", "zootopia")

#: Заголовки для HTTP-запросов. Возможно, стоит менять user-agent.
http_headers = {
    "connection": "close",
    "user-agent": "tabun_api/{} {}".format(__version__, utils.gen_user_agent()),
}

#: Регулярка для парсинга ссылки на пост.
post_url_regex = re.compile(r"/blog/(([A-z0-9_\-\.]{1,})/)?([0-9]{1,}).html")

#: Регулярка для парсинга прикреплённых файлов.
post_file_regex = re.compile(r'^Скачать \"(.+)" \(([0-9]*(\.[0-9]*)?) (Кб|Мб)\)$')

#: Логгер tabun_api.
logger = logging.getLogger(__name__)


class NoRedirect(urequest.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp

    http_error_301 = http_error_303 = http_error_307 = http_error_302


class TabunError(Exception):
    """Общее для библиотеки исключение.
    Содержит атрибут code с всякими разными циферками для разных типов исключения,
    обычно совпадает с HTTP-кодом ошибки при запросе.
    А в атрибуте ``message`` или текст, или снова код ошибки.

    Если возможно (например, при ошибке ввода-вывода), присутствует атрибут ``exc``
    с оригинальным исключением. Если это ``HTTPError``, то можно, например, вызвать
    ``exc.read()`` или ``user.saferead(exc)``.
    """

    def __init__(self, message=None, code=0, data=None, exc=None, msg=None):
        if msg is not None:
            assert message is None
            warnings.warn('TabunError(msg=...) is deprecated; use TabunError(message=...) instead of it', FutureWarning, stacklevel=2)
            message = msg
        message = text(message) if message else text(code)
        super(TabunError, self).__init__(message.encode('utf-8') if PY2 else message)
        self.message = message
        self.code = int(code)
        self.data = data
        self.exc = exc

    def __str__(self):
        return self.message.encode("utf-8") if PY2 else self.message

    def __unicode__(self):
        return self.message

    def __repr__(self):
        result = 'TabunError({})'.format(self._reprfields())
        return result.encode('utf-8') if PY2 else result

    def _reprfields(self):
        f = []
        if self.message is not None and self.message != text(self.code):
            f.append('message=' + repr(self.message))
        if self.code != 0:
            f.append('code=' + repr(self.code))
        if self.data is not None:
            f.append('data=' + repr(self.data))
        return ', '.join(f)


class TabunResultError(TabunError):
    """Исключение, содержащее текст ошибки, который вернул сервер.
    Как правило, это текст соответствующих всплывашек на сайте.
    Потомок ``TabunError``.
    """

    def __repr__(self):
        result = 'TabunResultError({})'.format(self._reprfields())
        return result.encode('utf-8') if PY2 else result


class Post(object):
    """Пост.

    Поля ``comments_new_count`` и ``favourited`` устарели; используйте контекст вместо них.

    Дополнительные значения контекста:

    * ``can_comment`` (True/False) — можно ли отправить комментарий
    * ``can_edit`` (True/False) — можно ли редактировать пост
    * ``can_delete`` — можно ли удалить пост
    * ``can_vote`` — можно ли голосовать за пост
    * ``vote_value`` (-1/0/1/None) — голос текущего пользователя
    * ``subscribed_to_comments`` (True/False) — подписан ли текущий пользователь на новые комментарии
    * ``unread_comments_count`` (int) — число новых комментариев (для постов из списка постов, иначе ноль)
    * ``favourited`` (True/False) — добавлен ли пост в избранное
    * ``favourite_tags`` (list) — теги избранного поста
    * ``can_save_favourite_tags`` (True/False) — можно ли редактировать теги избранного поста (обычно совпадает с ``favourited``)
    """

    def __init__(self, time, blog, post_id, author, title, draft,
                 vote_count, vote_total, body, tags, comments_count=None, comments_new_count=None,
                 short=False, private=False, blog_name=None, poll=None, favourite=0, favourited=None,
                 download=None, utctime=None, raw_body=None, cut_text=None, context=None):
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
        self.short = bool(short)
        self.private = bool(private)
        self.blog_name = text(blog_name) if blog_name else None
        self.poll = poll
        self.favourite = int(favourite) if favourite is not None else None
        if download and (not isinstance(download, Download) or download.post_id != self.post_id):
            raise ValueError
        self.download = download
        self.utctime = utctime
        self.cut_text = text(cut_text) if cut_text else None
        self.context = context or {}

        self.body, self.raw_body = utils.normalize_body(body, raw_body, cls='topic-content text')

        if favourited is not None:
            warnings.warn('Post(favourited=...) is deprecated; use context["favourited"] instead of it', FutureWarning, stacklevel=2)
            self.context['favourited'] = bool(favourited)

        if comments_new_count is not None:
            warnings.warn('Post(comments_new_count=...) is deprecated; use context["unread_comments_count"] instead of it', FutureWarning, stacklevel=2)
            self.context['unread_comments_count'] = comments_new_count

    def __repr__(self):
        o = "<post " + (self.blog or "[personal]") + '/' + text(self.post_id) + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')

    def hashsum(self, fields=None, debug=False):
        """Считает md5-хэш от конкатенации полей поста, разделённых нулевым байтом.

        Поддерживаются только следующие поля:
        post_id, time (в UTC), draft, author, blog, title, body (как необработанный html), tags.

        По умолчанию используются все они.

        Аргумент ``fields`` — список полей для использования
        (или любая другая коллекция, для которой работает проверка ``if field in fields``).

        Порядок и повторения полей в этом списке значения не имеют. Неизвестные поля игнорируются.

        При ``debug=True`` вместо хэша возвращается сырой список, используемый перед хэшированием,
        что позволит проверить правильность выбора полей.

        Возможные применения хэша —
        отслеживание изменений поста (но не мета-информации вроде названия блога и числа голосов)
        и идентификация разных версий постов.
        """

        buf = []

        # Not used: vote_count vote_total comments_count short private blog_name poll favourite download context

        if fields is None or 'post_id' in fields:
            buf.append(text(self.post_id))

        if fields is None or 'time' in fields:
            buf.append(text(self.utctime.strftime('%Y-%m-%dT%H:%M:%SZ')))

        if fields is None or 'draft' in fields:
            buf.append('1' if self.draft else '0')

        for field in ('author', 'blog', 'title'):
            if fields is None or field in fields:
                buf.append(getattr(self, field, None) or '')

        if fields is None or 'body' in fields:
            buf.append(self.raw_body)

        if fields is None or 'tags' in fields:
            buf.extend(self.tags)

        buf = [x.encode('utf-8') for x in buf]
        if debug:
            return buf
        h = md5(b'\x00'.join(buf))
        return h.hexdigest()

    @property
    def url(self):
        host = self.context.get('http_host') or http_host
        return host + '/blog/' + ((self.blog + '/') if self.blog else '') + text(self.post_id) + '.html'

    @property
    def favourited(self):
        warnings.warn('post.favourited is deprecated; use post.context.get("favourited") instead of it', FutureWarning, stacklevel=2)
        return self.context.get('favourited')

    @favourited.setter
    def favourited(self, value):
        warnings.warn('post.favourited is deprecated; use post.context.get("favourited") instead of it', FutureWarning, stacklevel=2)
        self.context['favourited'] = value

    @property
    def comments_new_count(self):
        warnings.warn('post.comments_new_count is deprecated; use post.context.get("unread_comments_count") instead of it', FutureWarning, stacklevel=2)
        return self.context.get('unread_comments_count')

    @comments_new_count.setter
    def comments_new_count(self, value):
        warnings.warn('post.comments_new_count is deprecated; use post.context.get("unread_comments_count") instead of it', FutureWarning, stacklevel=2)
        self.context['unread_comments_count'] = value


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
    """Коммент. Возможно, удалённый, поэтому следите, чтобы значения не были None!

    Поле ``favourited`` устарело; используйте ``comment.context.get('favourited')`` вместо него.

    Поле ``vote`` переименовано в ``vote_total``.

    Дополнительные значения контекста:

    * ``can_vote`` (True/False) — можно ли голосовать за комментарий
    * ``vote_value`` (-1/1/None) — голос текущего пользователя
    * ``favourited`` (True/False) — добавлен ли комментарий в избранное
    """

    def __init__(self, time, blog, post_id, comment_id, author, body, vote_total, parent_id=None,
                 post_title=None, unread=False, deleted=False, favourite=None, favourited=None,
                 utctime=None, raw_body=None, context=None, vote=None):
        self.time = time
        self.blog = text(blog) if blog else None
        self.post_id = int(post_id) if post_id else None
        self.comment_id = int(comment_id)
        self.author = text(author) if author else None
        self.vote_total = int(vote_total) if vote_total is not None else None
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
        self.utctime = utctime
        self.context = context or {}

        if vote is not None:
            warnings.warn('Comment(vote=...) is deprecated; use Comment(vote_total=...) instead of it', FutureWarning, stacklevel=2)
            self.vote_total = int(vote) if vote is not None else None

        if favourited is not None:
            warnings.warn('Comment(favourited=...) is deprecated; use context["favourited"] instead of it', FutureWarning, stacklevel=2)
            self.context['favourited'] = bool(favourited)

        self.body, self.raw_body = utils.normalize_body(body, raw_body)

    def __repr__(self):
        o = (
            "<" + ("deleted " if self.deleted else "") + "comment " +
            (((self.blog or '[personal]') + "/" + text(self.post_id) + "/") if self.post_id else "") +
            text(self.comment_id) + ">"
        )
        return o.encode('utf-8') if PY2 else o

    def hashsum(self, fields=None, debug=False):
        """Считает md5-хэш от конкатенации полей коммента, разделённых нулевым байтом.

        Поддерживаются только следующие поля:
        comment_id, time (в UTC), author, body (как необработанный html).

        По умолчанию используются все они. Аргумент ``fields`` — список полей для использования
        (или любая другая коллекция, для которой работает проверка ``if field in fields``).

        Порядок и повторения полей в этом списке значения не имеют. Неизвестные поля игнорируются.

        При ``debug=True`` вместо хэша возвращается сырой список, используемый перед хэшированием,
        что позволит проверить правильность выбора полей.
        """

        buf = []

        # Not used: blog post_id vote_total unread parent_id post_title deleted favourite context

        if fields is None or 'comment_id' in fields:
            buf.append(text(self.comment_id))

        if fields is None or 'time' in fields:
            buf.append(text(self.utctime.strftime('%Y-%m-%dT%H:%M:%SZ')))

        if fields is None or 'author' in fields:
            buf.append(self.author)

        if fields is None or 'body' in fields:
            buf.append(self.raw_body)

        buf = [x.encode('utf-8') for x in buf]
        if debug:
            return buf
        h = md5(b'\x00'.join(buf))
        return h.hexdigest()

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')

    @property
    def vote(self):
        warnings.warn('comment.vote is deprecated; use comment.vote_total instead of it', FutureWarning, stacklevel=2)
        return self.vote_total

    @vote.setter
    def vote(self, value):
        warnings.warn('comment.vote is deprecated; use comment.vote_total instead of it', FutureWarning, stacklevel=2)
        self.vote_total = value

    @property
    def favourited(self):
        warnings.warn('comment.favourited is deprecated; use comment.context.get("favourited") instead of it', FutureWarning, stacklevel=2)
        return self.context.get('favourited')

    @favourited.setter
    def favourited(self, value):
        warnings.warn('comment.favourited is deprecated; use comment.context.get("favourited") instead of it', FutureWarning, stacklevel=2)
        self.context['favourited'] = value


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
                 description=None, blogs=None, full=False, context=None, raw_description=None):
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

        self.full = bool(full)
        self.context = context or {}

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
    """Личное сообщение. При чтении списка сообщений некоторые поля могут быть None.
    Учтите, что для нового письма unread = True и context['unread_comments_count'] = 0.

    ``recipients_inactive`` — подмножество ``recipients``, содержащее имена пользователей,
    удаливших свою копию сообщения.

    Дополнительные параметры контекста:

    * ``favourited`` (True/False): добавлено ли письмо в избранное
    * ``last_is_incoming`` (True/False): является ли последний комментарий
      входящим (True) или исходящим (False) (только для списка писем)
    * ``unread_comments_count``: число непрочитанных комментариев в письме
      (только для списка писем)
    """

    def __init__(
        self, talk_id, recipients, unread, title, date,
        body=None, author=None, comments=None, utctime=None,
        recipients_inactive=(), comments_count=0, raw_body=None, context=None,
    ):
        self.talk_id = int(talk_id)
        self.recipients = [text(x) for x in recipients]
        self.recipients_inactive = [text(x) for x in recipients_inactive]
        self.unread = bool(unread)
        self.title = text(title)
        self.date = date
        self.author = text(author) if author else None
        self.comments = comments if comments else {}
        self.utctime = utctime
        self.comments_count = int(comments_count)
        self.context = context

        self.body, self.raw_body = utils.normalize_body(body, raw_body)

    def __repr__(self):
        o = "<talk " + text(self.talk_id) + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')


class ActivityItem(object):
    """Событие со страницы /stream/.

    Типы события (``obj.type``):

    * ``ActivityItem.WALL_ADD`` — добавление записи на стену пользователя (на Табуне отсутствует)
    * ``ActivityItem.POST_ADD`` — добавление поста
    * ``ActivityItem.COMMENT_ADD`` — добавление комментария
    * ``ActivityItem.BLOG_ADD`` — создание блога
    * ``ActivityItem.POST_VOTE`` — голосование за пост
    * ``ActivityItem.COMMENT_VOTE`` — голосование за комментарий
    * ``ActivityItem.BLOG_VOTE`` — голосование за блог
    * ``ActivityItem.USER_VOTE`` — голосование за пользователя (оценивающий в поле ``username``, оцениваемый — в ``data``)
    * ``ActivityItem.FRIEND_ADD`` — добавление друга (добавляющий в поле ``username``, добавляемый — в ``data``)
    * ``ActivityItem.JOIN_BLOG`` — вступление в блог (события выхода из блога на Табуне нет, ага)
    """

    WALL_ADD = 0
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
    Почти все методы могут кидаться исключением :class:`~tabun_api.TabunResultError`
    с текстом ошибки (который на сайте обычно показывается во всплывашке в углу).
    Плюс к этому может выкидываться :class:`~tabun_api.TabunError` при ошибках связи
    и других подобных нештатных событиях.

    Допустимые комбинации параметров (в квадратных скобках опциональные):

    * login + passwd [ + session_id]
    * session_id [+ key] — без куки key разлогинивает через некоторое время
    * login + session_id + security_ls_key [+ key] (с такой комбинацией конструктор отработает
      без запроса к серверу)
    * без параметров (анонимус)

    Если у метода есть параметр ``raw_data``, то через него можно передать код страницы,
    чтобы избежать лишнего запроса к Табуну. Если есть параметр ``url``, то при его указании
    открывается именно указанный URL вместо формирования стандартного с помощью других
    параметров метода.

    ``session_id`` — печенька (cookie), по которой идентифицируется пользователь (на самом Табуне
    называется TABUNSESSIONID).

    ``security_ls_key`` — секретный ключ движка LiveStreet для отправки POST-запросов (CSRF-токен).

    ``key`` - печенька неизвестного мне назначения.

    Можно не париться с ними, их автоматически пришлёт сервер во время инициализации объекта.
    А можно, например, не авторизоваться по логину и паролю, а выдрать из браузера печеньку
    TABUNSESSIONID, скормить в аргумент session_id и авторизоваться через неё.

    Конструктор также принимает кортеж proxy из трёх элементов ``(тип, хост, порт)`` для задания
    прокси-сервера. Сейчас поддерживаются только типы socks4 и socks5.
    Вместо передачи параметра можно установить переменную окружения
    ``TABUN_API_PROXY=тип,хост,порт`` — конструктор её подхватит.

    Если нужно парсить не Табун (можно частично парсить другие LiveStreet-сайты с основанным
    на synio шаблоном), то можно передать ``http_host``, чтобы не переопределять его
    во всём tabun_api.

    Если нужно добавить или переопределить какие-то HTTP-заголовки для конкретного объекта,
    можно запихнуть всё нужное в словарь ``override_headers``. При этом Cookie, Content-Type,
    X-Requested-With, Referer или ещё что-нибудь в любом случае затираются, если они нужны для
    отправки запроса (например, формы с созданием поста). Названия заголовков не чувствительны
    к регистру.

    У класса также есть следующие поля:

    * ``username`` — имя пользователя или None
    * ``talk_unread`` — число непрочитанных личных сообщений (обновляется после ``update_userinfo``)
    * ``skill`` — силушка (после ``update_userinfo``)
    * ``rating`` — кармушка (после ``update_userinfo``)
    * ``timeout`` — таймаут ожидания ответа от сервера (для функции ``urlopen``, по умолчанию 20)
    * ``session_id``, ``security_ls_key``, ``key`` — ну вы поняли
    * ``session_cookie_name`` — название печеньки, в которую положить ``session_id``
      (для Табуна TABUNSESSIONID, для других лайвстритов PHPSESSID)
    """

    session_id = None
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
    override_headers = {}

    def __init__(
        self, login=None, passwd=None, session_id=None, security_ls_key=None, key=None,
        proxy=None, http_host=None, session_cookie_name='TABUNSESSIONID', phpsessid=None
    ):
        if phpsessid is not None:
            warnings.warn('phpsessid is deprecated; use session_id instead of it', FutureWarning, stacklevel=2)
            session_id = phpsessid

        self.http_host = text(http_host).rstrip('/') if http_host else None
        self.session_cookie_name = text(session_cookie_name)

        self.jd = JSONDecoder()
        self.lock = threading.Lock()
        self.wait_lock = threading.Lock()

        self.configure_opener(proxy)

        # init
        self.last_query_time = 0
        self.talk_count = 0

        if session_id:
            self.session_id = text(session_id).split(";", 1)[0]
        if key:
            self.key = text(key)
        if self.session_id and security_ls_key:
            self.security_ls_key = text(security_ls_key)
            if login:
                self.username = text(login)
            return

        if not self.session_id or not security_ls_key:
            resp = self.urlopen("/")
            data = self._netwrap(resp.read, 1024 * 25)
            resp.close()

            cook = BaseCookie()
            if PY2:
                cook.load(resp.headers.get("set-cookie") or b'')
            else:
                for x in resp.headers.get_all("set-cookie") or ():
                    cook.load(x)
            if not self.session_id:
                self.session_id = cook.get(self.session_cookie_name)
                if self.session_id:
                    self.session_id = self.session_id.value
            if not self.key:
                ckey = cook.get("key")
                self.key = ckey.value if ckey else None

            self.update_userinfo(data)

            if self.security_ls_key == b'LIVESTREET_SECURITY_KEY':  # old security fix by Random
                csecurity_ls_key = cook.get("LIVESTREET_SECURITY_KEY")
                self.security_ls_key = csecurity_ls_key.value if csecurity_ls_key else None

        if login and passwd:
            self.login(login, passwd)

        # reset after urlopen
        self.last_query_time = 0
        self.talk_count = 0

    @property
    def phpsessid(self):
        warnings.warn('phpsessid is deprecated; use session_id instead of it', FutureWarning, stacklevel=2)
        return self.session_id

    @phpsessid.setter
    def phpsessid(self, value):
        warnings.warn('phpsessid is deprecated; use session_id instead of it', FutureWarning, stacklevel=2)
        self.session_id = value

    def configure_opener(self, proxy=None):
        handlers = []

        if proxy is None and os.getenv('TABUN_API_PROXY') and os.getenv('TABUN_API_PROXY').count(',') == 2:
            proxy = os.getenv('TABUN_API_PROXY').split(',')[:3]
        elif proxy:
            proxy = proxy.split(',') if isinstance(proxy, text_types) else list(proxy)[:3]

        if proxy:
            if proxy[0] not in ('socks4', 'socks5'):
                raise NotImplementedError('I can use only socks proxies now')
            proxy[2] = int(proxy[2])
            import socks
            from sockshandler import SocksiPyHandler
            if proxy[0] == 'socks5':
                handlers.append(SocksiPyHandler(socks.PROXY_TYPE_SOCKS5, proxy[1], proxy[2]))
            elif proxy[0] == 'socks4':
                handlers.append(SocksiPyHandler(socks.PROXY_TYPE_SOCKS4, proxy[1], proxy[2]))
            self.proxy = proxy

        # for thread safety
        self.opener = urequest.build_opener(*handlers)
        self.noredir = urequest.build_opener(*(handlers + [NoRedirect]))

    def update_security_ls_key(self, raw_data):
        """Выдирает security_ls_key из страницы. Вызывается из update_userinfo."""
        pos = raw_data.find(b"var LIVESTREET_SECURITY_KEY =")
        if pos > 0:
            ls_key = raw_data[pos:]
            ls_key = ls_key[ls_key.find(b"'") + 1:]
            self.security_ls_key = ls_key[:ls_key.find(b"'")].decode('utf-8', 'replace')

    def update_userinfo(self, raw_data):
        """Парсит security_ls_key, имя пользователя, рейтинг и число непрочитанных сообщений
        с переданного кода страницы и записывает в объект.
        Возвращает имя пользователя или None при его отсутствии.
        """
        self.update_security_ls_key(raw_data)

        userinfo = utils.find_substring(raw_data, b'<div class="dropdown-user"', b"<nav", with_end=False)
        if not userinfo:
            auth_panel = utils.find_substring(raw_data, b'<ul class="auth"', b'<nav', with_end=False)
            if auth_panel and 'Войти'.encode('utf-8') in auth_panel:
                self.username = None
                self.talk_count = 0
                self.skill = None
                self.rating = None
            else:
                logger.warning('update_userinfo received unknown data')
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
        data = self.saferead(resp)
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
        """Генерирует исключение, если нет ``session_id`` или ``security_ls_key``."""
        if not self.session_id or not self.security_ls_key:
            raise TabunError("Not logined")

    def get_main_context(self, raw_data, url=None):
        """Парсит основные параметры контекста со страницы Табуна.

        Возвращает что-то вроде такого::

            {
                'http_host': 'https://tabun.everypony.ru',
                'url': 'https://tabun.everypony.ru/blog/2.html',
                'username': 'Orhideous'
            }

        :param raw_data: исходный код страницы
        :type raw_data: bytes
        :param url: переопределение URL контекста при необходимости
        :type url: строка или None
        :rtype: dict
        """

        if url and url.startswith('/'):
            url = (self.http_host or http_host) + url
        context = {'http_host': self.http_host or http_host, 'url': url}

        userinfo = utils.find_substring(raw_data, b'<div class="dropdown-user"', b"<nav", with_end=False)
        if not userinfo:
            context['username'] = None
            auth_panel = utils.find_substring(raw_data, b'<ul class="auth"', b'<nav', with_end=False)
            if not auth_panel or 'Войти'.encode('utf-8') not in auth_panel:
                logger.warning('get_main_context received unknown userinfo')
        else:
            f = userinfo.find(b'class="username">')
            if f >= 0:
                username = userinfo[userinfo.find(b'>', f) + 1:userinfo.find(b'</', f)]
                context['username'] = username.decode('utf-8').strip()
            else:
                context['username'] = None

        return context

    def build_request(self, url, data=None, headers=None, with_cookies=True):
        """Собирает и возвращает объект ``Request``. Используется в методе :func:`~tabun_api.User.urlopen`."""

        if isinstance(url, binary):
            url = url.decode('utf-8')
        if not isinstance(url, urequest.Request):
            # 'abc абв\x7f' => 'abc%20%D0%B0%D0%B1%D0%B2%7F'
            url = ''.join((
                x if 0x21 <= ord(x) < 0x7f else urequest.quote(
                    x.encode('utf-8') if PY2 else x
                )) for x in url)
            if url.startswith('/'):
                url = (self.http_host or http_host) + url
            elif not url.startswith('http://') and not url.startswith('https://'):
                raise ValueError('Invalid URL: not http and not https')
            url = urequest.Request(url.encode('utf-8') if PY2 else url)
        if data is not None:
            url.data = data.encode('utf-8') if isinstance(data, text) else data

        request_headers = {k.title(): v for k, v in http_headers.items()}
        if self.override_headers:
            request_headers.update({k.title(): v for k, v in self.override_headers.items()})
        if headers:
            request_headers.update({k.title(): v for k, v in headers.items()})

        if with_cookies and self.session_id:
            request_headers['Cookie'] = ("%s=%s; key=%s; LIVESTREET_SECURITY_KEY=%s" % (
                self.session_cookie_name, self.session_id, self.key, self.security_ls_key
            )).encode('utf-8')

        for header, value in request_headers.items():
            if not isinstance(header, str):  # py2 and py3
                header = str(header)
            if isinstance(value, text):
                value = value.encode('utf-8')
            url.add_header(header, value)

        return url

    def _netwrap(self, func, *args, **kwargs):
        lock = kwargs.pop('_lock', False)
        try:
            if lock:
                with self.lock:
                    return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except (KeyboardInterrupt, SystemExit):
            raise
        except urequest.HTTPError as exc:
            if exc.getcode() == 404:
                data = exc.read(8192)
                if b'//projects.everypony.ru/error/main.css' in data:
                    raise TabunError('Static 404', -404)
            raise TabunError(code=exc.getcode(), exc=exc)
        except urequest.URLError as exc:
            raise TabunError(exc.reason, -abs(getattr(exc.reason, 'errno', 0)), exc=exc)
        except compat.HTTPException as exc:
            raise TabunError("HTTP error", -40, exc=exc)
        except socket_timeout as exc:
            raise TabunError("Timeout", -20, exc=exc)
        except IOError as exc:
            raise TabunError('IOError: ' + text(exc), -30, exc=exc)

    def send_request(self, request, redir=True, nowait=False, timeout=None):
        """Отправляет запрос (строку со ссылкой или объект ``Request``).
        Возвращает результат вызова ``urllib.urlopen`` (объект ``urllib.addinfourl``).
        Используется в методе ``urlopen``.
        Если установлен ``query_interval``, то метод может сделать паузу перед запросом
        для соблюдения интервала. Таймаут на эту паузу не влияет.
        """

        if self.query_interval <= 0:
            nowait = True

        # Выстраиваем «очередь» запросов с помощью блокировки;
        # каждый из запросов в этой блокировке поспит query_interval секунд
        if not nowait:
            self.wait_lock.acquire()

        try:
            # Если последний запрос был недавно, спим
            sleeptime = 0
            if not nowait:
                sleeptime = self.last_query_time - time.time() + self.query_interval
                if sleeptime > 0:
                    time.sleep(sleeptime)

            # Записываем время запроса перед отправкой, а не после, для компенсации сетевых задержек
            # А для компенсации локальных задержек время считаем сами вместо time.time()
            self.last_query_time = time.time() if sleeptime <= 0 else (self.last_query_time + self.query_interval)

            # И уже теперь готовим и отправляем запрос
            if timeout is None:
                timeout = self.timeout

            return self._netwrap(self.opener.open if redir else self.noredir.open, request, timeout=timeout, _lock=True)
        finally:
            if not nowait:
                self.wait_lock.release()

    def urlopen(self, url, data=None, headers=None, redir=True, nowait=False, with_cookies=True, timeout=None):
        """Отправляет HTTP-запрос и возвращает результат вызова ``urllib.urlopen`` (объект ``addinfourl``).

        Во избежание случайной DoS-атаки между несколькими запросами подряд имеется пауза
        в ``user.query_interval`` секунд (по умолчанию 0; отключается через ``nowait=True``).

        :param url: ссылка, на которую отправляется запрос, или сам объект ``Request``
        :type url: строка или Request
        :param data: содержимое тела HTTP. Если присутствует (даже пустое), то отправится POST-запрос
        :type data: строка (utf-8) или bytes или None
        :param headers: HTTP-заголовки (повторяться не могут)
        :type headers: кортежи из двух строк/bytes или словарь
        :param bool redir: следовать ли по перенаправлениям (3xx)
        :param bool nowait: игнорирование очереди запросов (которая нужна во избежание DoS)
        :param bool with_cookies: прикреплять ли session_id и остальные печеньки (отключайте для запросов не к Табуну)
        :param timeout: таймаут (по умолчанию ``user.timeout``)
        :type timeout: float или None
        :rtype: ``urllib.addinfourl`` / ``urllib.response.addinfourl``
        """

        req = self.build_request(url, data, headers, with_cookies)
        return self.send_request(req, redir, nowait, timeout)

    def urlread(self, url, data=None, headers=None, redir=True, nowait=False, with_cookies=True, timeout=None):
        """Как ``return self.urlopen(*args, **kwargs).read()``, но с перехватом
        исключений, возникших в процессе чтения (см. :func:`~tabun_api.User.saferead`).
        """

        req = self.build_request(url, data, headers, with_cookies)
        resp = self.send_request(req, redir, nowait, timeout)
        try:
            return self._netwrap(resp.read)
        finally:
            resp.close()

    def saferead(self, resp):
        """Вызывает функцию read у переданного объекта с перехватом ошибок
        ввода-вывода и выкидыванием :class:`~tabun_api.TabunError` вместо них
        (оригинальное исключение может быть доступно через поле ``exc``).
        Также вызывает метод ``close`` при его наличии.
        """

        try:
            return self._netwrap(resp.read)
        finally:
            if hasattr(resp, 'close'):
                resp.close()

    def send_form(self, url, fields=(), files=(), headers=None, redir=True):
        """Формирует multipart/form-data запрос и отправляет его через метод
        :func:`~tabun_api.User.urlopen` с аргументами по умолчанию.

        Значения полей и файлов могут быть строками (закодируются в utf-8),
        bytes или числами (будут преобразованы в строку).

        :param url: ссылка, на которую отправляется запрос, или сам объект ``Request``
        :type url: строка или Request
        :param fields: простые поля запроса
        :type fields: коллекция кортежей (название, значение)
        :param fields: файлы запроса (MIME-тип будет выбран по расширению)
        :type fields: коллекция кортежей (название, имя файла, значение)
        :param headers: HTTP-заголовки (повторяться не могут)
        :type headers: кортежи из двух строк/bytes или словарь
        :param bool redir: следовать ли по перенаправлениям (3xx)
        :rtype: ``urllib.addinfourl`` / ``urllib.response.addinfourl``
        """

        content_type, data = utils.encode_multipart_formdata(fields, files)
        headers = dict(headers or ())
        headers['content-type'] = content_type
        return self.urlopen(url, data, headers, redir)

    def send_form_and_read(self, url, fields=(), files=(), headers=None, redir=True):
        """Аналогично :func:`~tabun_api.User.send_form`, но сразу возвращает тело ответа (bytes)."""
        content_type, data = utils.encode_multipart_formdata(fields, files)
        headers = dict(headers or ())
        headers['content-type'] = content_type
        return self.urlread(url, data, headers, redir)

    def ajax(self, url, fields=None, files=(), headers=None, throw_if_error=True):
        """Отправляет ajax-запрос и возвращает распарсенный json-ответ.
        Или кидается исключением :class:`~tabun_api.TabunResultError` в случае ошибки.

        :param url: ссылка, на которую отправляется запрос, или сам объект ``Request``
        :type url: строка или Request
        :param fields: простые поля запроса
        :type fields: коллекция кортежей (название, значение)
        :param fields: файлы запроса (MIME-тип будет выбран по расширению)
        :type fields: коллекция кортежей (название, имя файла, значение)
        :param headers: HTTP-заголовки (повторяться не могут)
        :type headers: кортежи из двух строк/bytes или словарь
        :param bool throw_if_error: выкидывать ли TabunResultError, если придёт ошибка
        :rtype: dict
        :raises TabunResultError: если сервер вернёт непустой ``bStateError`` при ``throw_if_error=True``
        """

        self.check_login()
        headers = dict(headers or ())
        headers['x-requested-with'] = 'XMLHttpRequest'
        fields['security_ls_key'] = self.security_ls_key
        data = self.send_form_and_read(url, fields or {}, files, headers=headers)

        if data.startswith(b'<textarea>{'):
            # Вроде это какой-то костыль для старых браузеров
            data = utils.find_substring(data, b'>', b'</', extend=True, with_start=False, with_end=False)
            data = html_unescape(data.decode('utf-8'))
        else:
            try:
                data = data.decode('utf-8')
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                raise TabunResultError(data.decode('utf-8', 'replace'))

        try:
            data = self.jd.decode(data)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            raise TabunResultError(data)

        if throw_if_error and data['bStateError']:
            raise TabunResultError(data['sMsg'], data=data)

        return data

    def upload_image_file(self, fp, title='', parse_link=False, filename=None):
        """Загружает файл с картинкой на Табун.

        :param fp: путь к файлу или файловый объект
        :type fp: строка или file
        :param title: заголовок картинки
        :type title: строка
        :param bool parse_link: если True, пытаться достать ссылку из html-кода вместо возвращения самого html-кода
        :param filename: имя файла, если передан файловый объект (по его расширению вычисляется Content-Type)
        :type filename: строка
        :rtype: строка
        """

        if isinstance(fp, text_types):
            with open(fp, 'rb') as fpt:
                data = fpt.read()
            filename = os.path.split(fp)[-1] or None
        else:
            data = fp.read()
        assert isinstance(data, binary)

        if not filename:
            if data.startswith(b'\xff\xd8\xff\xe0'):
                filename = 'image.jpg'
            elif data.startswith(b'GIF8'):
                filename = 'image.gif'
            elif data.startswith(b'\x89PNG\r\n\x1a\n'):
                filename = 'image.png'
            else:
                filename = 'rare_image.png'  # сервер сам разрулит

        html = self.ajax(
            '/ajax/upload/image/',
            fields={'title': title},
            files=[('img_file', filename, data)]
        )['sText']
        if not parse_link:
            return html

        return utils.parse_html_fragment(html)[0].get('src', '')

    def upload_image_link(self, url, title='', parse_link=False):
        """Загружает на Табун картинку по ссылке.

        :param url: ссылка на файл или файловый объект
        :type url: строка
        :param title: заголовок картинки
        :type title: строка
        :param bool parse_link: если True, пытаться достать ссылку из html-кода вместо возвращения самого html-кода
        :rtype: строка
        """

        html = self.ajax(
            '/ajax/upload/image/',
            fields={'title': title, 'img_url': url},
        )['sText']
        if not parse_link:
            return html

        return utils.parse_html_fragment(html)[0].get('src', '')

    def add_post(self, blog_id, title, body, tags, draft=False, check_if_error=False):
        """Отправляет пост и возвращает имя блога с номером поста.

        :param blog_id: ID блога, в который добавляется пост
        :type blog_id: int
        :param title: заголовок создаваемого поста
        :type title: строка
        :param body: текст поста
        :type body: строка
        :param tags: теги поста
        :type tags: строка или коллекция строк
        :param draft: создание в черновиках вместо публикации
        :type draft: bool
        :param check_if_error: проверяет наличие поста по заголовку даже в случае ошибки
          (если, например, таймаут или 404, но пост, как иногда бывает, добавляется)
        :type check_if_error: bool
        :returns: кортеж ``(blog, post_id)`` или ``(None, None)`` при неудаче
        """

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
            data = self.saferead(result)
            error = utils.find_substring(data, b'<ul class="system-message-error">', b'</ul>', with_start=False, with_end=False)
            if error and b':' in error:
                error = utils.find_substring(error.decode('utf-8', 'replace'), ':', '</li>', extend=True, with_start=False, with_end=False).strip()
                raise TabunResultError(error)
            link = result.headers.get('location')
        except TabunResultError:
            raise
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
        """Создает опрос и возвращает имя блога с номером поста.

        :param blog_id: ID блога, в который добавляется опрос
        :type blog_id: int
        :param title: заголовок создаваемого поста (должен содержать сам вопрос)
        :type title: строка
        :param choices: варианты ответов (не более 20)
        :type choices: коллекция строк
        :param body: текст поста
        :type body: строка
        :param tags: теги поста
        :type tags: строка или коллекция строк
        :param draft: создание в черновиках вместо публикации
        :type draft: bool
        :param check_if_error: проверяет наличие поста по заголовку даже в случае ошибки
          (если, например, таймаут или 404, но пост, как иногда бывает, добавляется)
        :type check_if_error: bool
        :returns: кортеж ``(blog, post_id)`` или ``(None, None)`` при неудаче
        """

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
            data = self.saferead(result)
            error = utils.find_substring(data, b'<ul class="system-message-error">', b'</ul>', with_start=False, with_end=False)
            if error and b':' in error:
                error = utils.find_substring(error.decode('utf-8', 'replace'), ':', '</li>', extend=True, with_start=False, with_end=False).strip()
                raise TabunResultError(error)
            link = result.headers.get('location')
        except TabunResultError:
            raise
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
        """Создаёт блог и возвращает его url-имя или None в случае неудачи.

        :param title: заголовок нового блога
        :type title: строка
        :param url: url-имя блога (на латинице без пробелов)
        :type url: строка
        :param description: описание блога (допустим HTML-код)
        :type description: строка
        :param int rating_limit: минимальный рейтинг пользователя, при котором можно писать в блог
        :param bool closed: сделать блог закрытым (с доступом к нему по инвайтам)
        :rtype: строка или None
        """

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
        """Редактирует блог и возвращает его url-имя или None в случае неудачи.

        :param int blog_id: ID блога, который редактируется
        :param title: заголовок блога
        :type title: строка
        :param description: описание блога (допустим HTML-код)
        :type description: строка
        :param int rating_limit: минимальный рейтинг пользователя, при котором можно писать в блог
        :param bool closed: сделать блог закрытым (с доступом к нему по инвайтам)
        :rtype: строка или None
        """

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
        """Удаляет блог.

        :param int blog_id: ID удалямого блога
        """

        self.check_login()
        resp = self.urlopen(
            url='/blog/delete/' + text(int(blog_id)) + '/?security_ls_key=' + self.security_ls_key,
            headers={"referer": (self.http_host or http_host) + "/"},
            redir=False
        )
        if resp.getcode() // 100 != 3:
            raise TabunError('Cannot delete blog', code=resp.getcode())

    def preview_post(self, blog_id, title, body, tags):
        """Возвращает HTML-код предпросмотра поста (сам пост плюс мусор типа заголовка «Предпросмотр»).

        :param int blog_id: ID блога, в который добавляется пост
        :param title: заголовок создаваемого поста
        :type title: строка
        :param body: текст поста
        :type body: строка
        :param tags: теги поста
        :type tags: строка или коллекция строк
        :rtype: строка
        """

        self.check_login()

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

        data = self.send_form_and_read('/ajax/preview/topic/', fields, (), headers={'x-requested-with': 'XMLHttpRequest'})
        node = utils.parse_html_fragment(data)[0]
        data = node.text
        result = self.jd.decode(data)
        if result['bStateError']:
            raise TabunResultError(result['sMsg'])
        return result['sText']

    def delete_post(self, post_id):
        """Удаляет пост.

        :param int post_id: ID удаляемого поста
        """

        self.check_login()
        resp = self.urlopen(
            url='/topic/delete/' + text(int(post_id)) + '/?security_ls_key=' + self.security_ls_key,
            headers={"referer": (self.http_host or http_host) + "/blog/" + text(post_id) + ".html"},
            redir=False
        )
        if resp.getcode() // 100 != 3:
            raise TabunError('Cannot delete post', code=resp.getcode())

    def subscribe_to_new_comments(self, post_id, subscribed, mail=None):
        """Меняет статус подписки на новые комментарии у поста.

        :param int post_id: ID поста
        :param bool subscribed: True — подписаться, False — отписаться
        :param mail: неизвестно
        :type mail: строка
        :rtype: None
        """

        self.ajax(
            '/subscribe/ajax-subscribe-toggle/',
            {
                'target_type': 'topic_new_comment',
                'target_id': int(post_id),
                'value': 1 if subscribed else 0,
                'mail': text(mail) if mail else '',
            }
        )

    def toggle_subscription_to_blog(self, blog_id):
        """Подписывается на блог/отписывается от блога и возвращает новое состояние: True - подписан, False - не подписан.

        :param int blog_id: ID блога
        :rtype: bool
        """

        return self.ajax('/blog/ajaxblogjoin/', {'idBlog': int(blog_id)})['bState']

    def toggle_blog_subscribe(self, blog_id):
        warnings.warn('toggle_blog_subscribe is deprecated; use toggle_subscription_to_blog instead of it', FutureWarning, stacklevel=2)
        return self.toggle_subscription_to_blog(blog_id)

    def comment(self, target_id=None, body=None, reply=0, typ="blog", post_id=None):
        """Отправляет коммент и возвращает его номер.

        :param int target_id: ID поста или лички, куда отправляется коммент
        :param body: текст комментария
        :type body: строка
        :param int reply: ID комментария, на который отправляется ответ (0 — не является ответом)
        :param typ: ``blog`` — пост, ``talk`` — личное сообщение
        :type typ: строка
        :return: ID созданного комментария
        :rtype: int
        """

        if post_id is not None:
            warnings.warn('comment(post_id=...) is deprecated; use comment(target_id=...) instead of it', FutureWarning, stacklevel=2)
            target_id = post_id
        elif target_id is None:
            raise TypeError('target_id can\'t be None')
        if body is None:
            raise TypeError('body can\'t be None')

        fields = {
            'comment_text': text(body),
            'reply': int(reply),
            'cmt_target_id': int(target_id)
        }

        return self.ajax("/" + (typ if typ in ("blog", "talk") else "blog") + "/ajaxaddcomment/", fields)['sCommentId']

    def get_recommendations(self, raw_data):
        """Возвращает со страницы список постов, которые советует Дискорд.
        После обновления Табуна не работает.
        """

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
        """Возвращает список постов со страницы или RSS.
        Если постов нет — кидает исключение TabunError("No post").

        Сортирует в порядке, обратном порядку на странице (т.е. на странице новые
        посты вверху, а в возвращаемом списке новые посты в его конце).

        :param url: ссылка на страницу, с которой достать посты
        :type url: строка
        :param bytes raw_data: код страницы (чтобы не скачивать его по ссылке)
        :rtype: список объектов :class:`~tabun_api.Post`
        """

        if not raw_data:
            resp = self.urlopen(url)
            url = resp.url
            raw_data = self.saferead(resp)
            del resp
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

        context = self.get_main_context(raw_data, url=url)

        data = utils.find_substring(raw_data, b"<article ", b"</article> <!-- /.topic -->", extend=True)
        if not data:
            raise TabunError("No post")

        can_be_short = not url.split('?', 1)[0].endswith('.html')
        escaped_data = utils.escape_comment_contents(utils.escape_topic_contents(data, can_be_short))
        # items = filter(lambda x: not isinstance(x, text_types) and x.tag == "article", utils.parse_html_fragment(escaped_data))
        items = [x for x in utils.parse_html_fragment(escaped_data) if not isinstance(x, text_types) and x.tag == "article"]
        items.reverse()

        for item in items:
            post = parse_post(item, context=context)
            if post:
                posts.append(post)

        return posts

    def get_post(self, post_id, blog=None, raw_data=None):
        """Возвращает пост по номеру.

        Рекомендуется указать url-имя блога, чтобы избежать перенаправления и лишнего запроса.

        Если поста нет - кидается исключением ``TabunError("No post")``.
        В случае проблем с парсингом может вернуть ``None``.

        Также, в отличие от :func:`~tabun_api.User.get_posts`, добавляет can_comment в контекст.

        :param int post_id: ID скачиваемого поста
        :param blog: url-имя блога (опционально, для оптимизации)
        :type blog: строка
        :param bytes raw_data: код страницы (чтобы не скачивать его)
        :rtype: :class:`~tabun_api.Post` или ``None``
        """

        if blog:
            url = "/blog/" + text(blog) + "/" + text(post_id) + ".html"
        else:
            url = "/blog/" + text(post_id) + ".html"

        if not raw_data:
            resp = self.urlopen(url)
            url = resp.url
            raw_data = self.saferead(resp)
            del resp

        posts = self.get_posts(url, raw_data=raw_data)
        if not posts:
            return

        if len(posts) != 1:
            raise TabunError('Many posts on page {}'.format(repr(url)))
        post = posts[0]

        comments_count = utils.find_substring(raw_data, b'<div class="comments" id="comments"', b'</h3>')
        if comments_count:
            comments_count = utils.find_substring(raw_data, b'<span id="count-comments">', b'</span>', with_start=False, with_end=False)
            post.comments_count = int(comments_count.strip())
            post.context['unread_comments_count'] = 0

        post.context['can_comment'] = b'<h4 class="reply-header" id="comment_id_0">' in raw_data

        f = raw_data.find(b'<div class="comments" id="comments">')
        if f >= 0:
            post.context['subscribed_to_comments'] = raw_data.find(b'<input checked="checked" type="checkbox" id="comment_subscribe"', f, f + 1000) >= 0

        return post

    def get_comments(self, url="/comments/", raw_data=None):
        """Парсит комменты со страницы по указанной ссылке.
        Допустимы как страницы постов, так и страницы ленты комментов.
        Но из ленты комментов доступны не все данные ``context``.

        :param url: ссылка на страницу, с которой достать комменты
        :type url: строка
        :param bytes raw_data: код страницы (чтобы не скачивать его по ссылке)
        :rtype: dict {id: :class:`~tabun_api.Comment`, ...}
        """

        if not raw_data:
            resp = self.urlopen(url)
            url = resp.url
            raw_data = self.saferead(resp)
            del resp
        blog, post_id = parse_post_url(url)

        data = utils.find_substring(raw_data, b'<div class="comments', b'<!-- /content -->', extend=True, with_end=False)
        if not data:
            return {}
        data = utils.replace_cloudflare_emails(data)
        escaped_data = utils.escape_comment_contents(utils.escape_topic_contents(data, True))
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
        context = self.get_main_context(raw_data, url=url)

        for sect in raw_comms:
            c = parse_comment(sect, post_id, blog, context=context)
            if c:
                comms[c.comment_id] = c
            else:
                if sect.get("id", "").find("comment_id_") == 0:
                    c = parse_deleted_comment(sect, post_id, blog, context=context)
                    if c:
                        comms[c.comment_id] = c
                    else:
                        logger.warning('Cannot parse deleted comment %s (url: %s)', sect.get('id'), url)
                else:
                    logger.warning('Unknown comment format %s (url: %s)', sect.get('id'), url)

        return comms

    def get_blogs_list(self, page=1, order_by="blog_rating", order_way="desc", url=None):
        """Возвращает список объектов Blog."""
        if not url:
            url = "/blogs/" + (("page" + text(page) + "/") if page > 1 else "")
            url += "?order=" + text(order_by)
            url += "&order_way=" + text(order_way)

        data = self.urlread(url)
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
            raw_data = self.urlread("/blog/" + text(blog) + "/")
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
        """Возвращает пост и словарь комментариев.
        По сути просто вызывает метод :func:`~tabun_api.User.get_post` и :func:`~tabun_api.User.get_comments`.

        :param int post_id: ID скачиваемого поста
        :param blog: url-имя блога (опционально, для оптимизации)
        :param bytes raw_data: код страницы (чтобы не скачивать его)
        :return: ``(Post, {id: Comment, ...})``
        :rtype: tuple
        """

        post_id = int(post_id)
        if not raw_data:
            resp = self.urlopen("/blog/" + ((text(blog) + "/") if blog else "") + text(post_id) + ".html")
            url = resp.url
            raw_data = self.saferead(resp)
            del resp

        post = self.get_posts(url=url, raw_data=raw_data)
        comments = self.get_comments(url=url, raw_data=raw_data)

        return (post[0] if post else None), comments

    def get_comments_from(self, target_id=None, comment_id=0, typ="blog", post_id=None):
        """Возвращает словарь комментариев к посту или личке c id больше чем `comment_id`.
        На сайте используется для подгрузки новых комментариев (ajaxresponsecomment).

        :param int target_id: ID поста или личного сообщения, с которого загружать комментарии
        :param int comment_id: ID комментария, начиная с которого (но не включая его самого) запросить комментарии
        :param typ: ``blog`` — пост, ``talk`` — личное сообщение
        :rtype: dict {id: :class:`~tabun_api.Comment`, ...}
        """

        if post_id is not None:
            warnings.warn('get_comments_from(post_id=...) is deprecated; use get_comments_from(target_id=...) instead of it', FutureWarning, stacklevel=2)
            target_id = post_id
        elif target_id is None:
            raise TypeError('target_id can\'t be None')

        target_id = int(target_id)
        comment_id = int(comment_id) if comment_id else 0

        url = "/" + (typ if typ in ("blog", "talk") else "blog") + "/ajaxresponsecomment/"

        try:
            data = self.ajax(url, {'idCommentLast': comment_id, 'idTarget': target_id, 'typeTarget': 'topic'})
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
        # comments/pid для Табуна, aComments/idParent для остальных LiveStreet
        # (При отсутствии комментариев в comments почему-то возвращается список вместо словаря)
        comms_list = data['comments'].values() if data.get('comments') else data['aComments']
        for comm in comms_list:
            node = utils.parse_html_fragment(utils.escape_comment_contents(comm['html'].encode('utf-8')))
            pcomm = parse_comment(
                node[0],
                target_id if typ == 'blog' else None,
                None,
                comm['pid'] if 'pid' in comm else comm['idParent']
            )
            if pcomm:
                comms[pcomm.comment_id] = pcomm
            else:
                logger.warning('Cannot parse ajax comment from %s', target_id)

        return comms

    def get_stream_comments(self):
        """Возвращает «Прямой эфир» - объекты :func:`~tabun_api.StreamItem`."""
        self.check_login()
        data = self.urlread(
            "/ajax/stream/comment/",
            "security_ls_key=" + urequest.quote(self.security_ls_key)
        )

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
                vote_count=None, vote_total=None, body=None, tags=[], comments_count=comments_count,
                context=None
            ))

        return items

    def get_short_blogs_list(self, raw_data=None):
        """Возвращает пустой список. После обновления Табуна не работает, функция оставлена для обратной совместимости.
        """
        return []

    def get_people_list(self, page=1, order_by="user_rating", order_way="desc", url=None):
        """Загружает список пользователей со страницы ``/people/``.

        :param int page: страница
        :param order_by: сортировка (``user_rating``, ``user_skill``, ``user_login`` или ``user_id``)
        :type order_by: строка
        :param order_way: сортировка по возрастанию (``asc``) или убыванию (``desc``)
        :type order_way: строка
        :param url: ссылка, с которых скачать пользователей (если указать, игнорируются все предыдущие параметры)
        :type url: строка
        :rtype: список из :class:`~tabun_api.UserInfo`
        """

        if not url:
            url = "/people/" + ("index/page" + text(page) + "/" if page > 1 else "")
            url += "?order=" + text(order_by)
            url += "&order_way=" + text(order_way)

        data = self.urlread(url)
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

            peoples.append(UserInfo(utils.parse_avatar_url(userpic[0])[0] or -1, username[0], realname, skill[0], rating[0], userpic=userpic[0]), full=False)

        return peoples

    def get_profile(self, username=None, url=None, raw_data=None):
        """Получает информацию об указанном пользователе.

        В ``raw_data`` можно указать не только страницу с профилем пользователя, но также
        список публикаций или комментариев и т.п. — в таком случае будет получена частичная
        информация, доступная на этих страницах.

        :param username: имя пользователя
        :type username: строка
        :param url: ссылка на страницу, с которой парсить информацию
        :type url: строка
        :param bytes raw_data: код страницы (чтобы не скачивать его)
        :rtype: :class:`~tabun_api.UserInfo`
        """

        if not url:
            url = '/profile/' + urequest.quote(text(username).encode('utf-8')) + '/'

        if not raw_data:
            raw_data = self.urlread(url)

        data = utils.find_substring(raw_data, b'<div id="content"', b'<!-- /content ', extend=True, with_end=False)
        if not data:
            return
        data = utils.replace_cloudflare_emails(data)
        node = utils.parse_html_fragment(data)
        if not node:
            return
        node = node[0]

        # Блок в самом верху всех страниц профиля
        profile = node.xpath('div[@class="profile"]')[0]

        username = profile.xpath('h2[@itemprop="nickname"]/text()')[0]
        realname = profile.xpath('p[@class="user-name"]/text()')

        skill = float(profile.xpath('div[@class="strength"]/div[1]/text()')[0])
        rating_elem = profile.xpath('div[@class="vote-profile"]/div[1]')[0]
        user_id = int(rating_elem.get("id").rsplit("_")[-1])
        rating = float(rating_elem.findall('div')[1].find('span').text.strip().replace('+', ''))

        full = True

        # Блок с основной информацией на странице /profile/xxx/
        about = node.xpath('div[@class="profile-info-about"]')
        if about:
            about = about[0]
            userpic = about.xpath('a[1]/img')[0].get('src')
            description = about.xpath('div[@class="text"]')  # TODO: escape contents
        else:
            about = None
            userpic = None
            description = None
            full = False

        birthday = None
        registered = None
        last_activity = None
        gender = None

        # Блок с чуть более подробной информацией на /profile/xxx/ (личное и активность)
        profile_left = node.xpath('div[@class="wrapper"]/div[@class="profile-left"]')
        if profile_left:
            profile_left = profile_left[0]
            profile_items = profile_left.xpath('ul[@class="profile-dotted-list"]/li')
            blogs = {
                'owner': [],
                'admin': [],
                'moderator': [],
                'member': []
            }
        else:
            profile_items = []
            blogs = None
            full = False

        for ul in profile_items:
            name = ul.find('span').text.strip()
            value = ul.find('strong')
            if name == 'Дата рождения:':
                birthday = time.strptime(utils.mon2num(value.text), '%d %m %Y')
            elif name == 'Зарегистрирован:':
                try:
                    registered = time.strptime(utils.mon2num(value.text), '%d %m %Y, %H:%M')
                except ValueError:
                    if username != 'guest':  # 30 ноября -0001, 00:00
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

        if registered is None and full:
            # забагованная учётка Tailsik208 со смайликом >_< (была когда-то)
            logger.warning('Profile %s: registered date is None! Please report to andreymal.', username)
            registered = time.gmtime(0)
            description = []

        # Сайдбар с фотографией и количеством публикаций
        sidebar = utils.find_substring(raw_data, b'<aside id="sidebar">', b'</aside>')
        if sidebar:
            sidebar = utils.parse_html_fragment(sidebar)[0]
            foto = sidebar.xpath('//img[@id="foto-img"]')
        else:
            full = False
            foto = None

        foto = foto[0].get('src', '') if foto else None
        if not foto or foto.endswith('user_photo_male.png') or foto.endswith('user_photo_female.png'):
            foto = None

        context = self.get_main_context(raw_data, url=url)

        # TODO: количество публикаций
        # TODO: заметка

        return UserInfo(
            user_id, username, realname[0] if realname else None, skill,
            rating, userpic, foto, gender, birthday, registered, last_activity,
            description[0] if description else None, blogs,
            full=full, context=context,
        )

    def poll_answer(self, post_id, answer=-1):
        """Проголосовать в опросе. -1 - воздержаться.

        :param int post_id: ID поста с опросом, в котором голосуем
        :param int answer: порядковый номер ответа (отсчёт с нуля)
        :return: обновлённые данные опроса
        :rtype: :class:`~tabun_api.Poll`
        """

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

    def favourite_talk(self, talk_id, type=True):
        """Добавляет (type=True) личное сообщение в избранное или убирает (type=False) оттуда.
        Возвращает новое состояние (1/0)."""
        fields = {
            "idTalk": int(talk_id),
            "type": "1" if type else "0"
        }

        return 1 if self.ajax('/ajax/favourite/talk/', fields)['bState'] else 0

    def save_favourite_tags(self, target_id, tags, target_type='topic'):
        """Редактирует теги избранного поста и возвращает
        новый их список (элементы — словари с ключами tag и url).

        :param int target_id: ID поста
        :param tags: новые теги (старые будут удалены)
        :type tags: строка или коллекция строк
        :param target_type: неизвестно
        :type target_type: строка
        :rtype: список словарей
        """

        fields = {
            "target_type": target_type,
            "target_id": int(target_id),
            "tags": tags if isinstance(tags, text) else ', '.join(tags)
        }

        return self.ajax('/ajax/favourite/save-tags/', fields)['aTags']

    def edit_comment(self, comment_id, text):
        """Редактирует комментарий и возвращает новое тело комментария. После обновления Табуна не работает."""
        fields = {
            "commentId": int(comment_id),
            "text": text.encode("utf-8")
        }

        data = self.ajax('/role_ajax/savecomment/', fields)
        # TODO: raw_body
        return utils.parse_html_fragment('<div class="text">' + data['sText'] + '</div>')[0]

    def get_editable_post(self, post_id, raw_data=None):
        """Возвращает blog_id, заголовок, исходный код поста, список тегов
        и галочку закрытия комментариев (True/False).

        :param int post_id: ID поста (должен быть доступ на редактирование)
        :param bytes raw_data: код страницы (чтобы не скачивать его)
        :rtype: (int, строка, строка, список строк, bool)
        """

        if not raw_data:
            raw_data = self.urlread("/topic/edit/" + text(int(post_id)) + "/")

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
        """Возвращает заголовок блога, URL, тип (True - закрытый, False - открытый),
        описание и ограничение рейтинга.

        :param int blog_id: ID блога (должен быть доступ на редактирование)
        :param bytes raw_data: код страницы (чтобы не скачивать его)
        :rtype: (строка, строка, bool, строка, float)
        """

        if not raw_data:
            raw_data = self.urlread("/blog/edit/" + text(int(blog_id)) + "/")

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

    def edit_post(self, post_id, blog_id, title, body, tags, forbid_comment=False, draft=False):
        """Редактирует пост и возвращает его блог и номер.

        :param int post_id: ID редактируемого поста
        :param int blog_id: ID блога, в который поместить пост
        :param title: заголовок поста
        :type title: строка
        :param body: текст поста
        :type body: строка
        :param tags: теги поста
        :type tags: строка или коллекция строк
        :param bool forbid_comment: закрыть (True) или открыть (False) написание комментариев
        :param bool draft: перемещение в черновики (True) или публикация из черновиков (False)
        :return: кортеж ``(blog, post_id)`` или ``(None, None)`` при неудаче
        """

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
        if forbid_comment:
            fields['topic_forbid_comment'] = '1'

        if draft:
            fields['submit_topic_save'] = "Сохранить в черновиках"
        else:
            fields['submit_topic_publish'] = "Опубликовать"

        link = self.send_form('/topic/edit/' + text(int(post_id)) + '/', fields, redir=False).headers.get('location')
        return parse_post_url(link)

    def invite(self, blog_id, users=None, username=None):
        """Отправляет инвайт в блог с указанным номером указанному пользователю
        (или пользователям, если указать несколько через запятую).

        Возвращает словарь, который содержит пары юзернейм-текст ошибки в случае,
        если кому-то инвайт не отправился. Если всё хорошо, то словарь пустой.

        :param int blog_id: ID блога, инвайты для которого рассылаются
        :param users: пользователи, которым рассылаются инвайты
        :type users: строка (с никами через запятую) или коллекция строк
        :rtype: dict
        """

        if username is not None:
            warnings.warn('invite(username=...) is deprecated; use invite(users=...) instead of it', FutureWarning, stacklevel=2)
            users = username
        elif not users:
            raise TypeError('users can\'t be empty')

        self.check_login()

        fields = {
            "users": users if isinstance(users, text) else ', '.join(users),
            "idBlog": text(int(blog_id) if blog_id else 0),
            'security_ls_key': self.security_ls_key,
        }

        data = self.send_form_and_read("/blog/ajaxaddbloginvite/", fields)
        result = self.jd.decode(data.decode('utf-8'))
        if result['bStateError']:
            raise TabunResultError(result['sMsg'])

        users = {}
        for x in result['aUsers']:
            if x['bStateError']:
                users[x['sUserLogin']] = x['sMsg']

        return users

    def add_talk(self, talk_users, title, body):
        """Отправляет новое личное сообщение пользователям.

        :param talk_users: имена пользователей, для которых создаётся сообщение (если строка, то имена через запятую)
        :type talk_users: строка или коллекция строк
        :param title: заголовок сообщения
        :type title: строка
        :param body: текст сообщения
        :type body: строка
        :return: ID созданного личного сообщения
        :rtype: int
        """

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
        data = self.saferead(result)
        errors = utils.find_substring(data, b'<ul class="system-message-error">', b'</ul>')
        if errors and b':' in errors:
            errors = utils.parse_html_fragment(errors)[0]
            errors = '; '.join(x.text_content().split('Ошибка:', 1)[-1].strip() for x in errors.findall('li'))
            raise TabunResultError(errors)

        link = result.headers.get('location')
        if '/talk/read/' in link:
            return int(link.rstrip('/').rsplit('/', 1)[-1])

    def get_talk_list(self, page=1, raw_data=None):
        """Возвращает список объектов :class:`~tabun_api.TalkItem` с личными сообщениями."""
        url = "/talk/inbox/page{}/".format(int(page))
        if not raw_data:
            self.check_login()
            raw_data = self.urlread(url)

        raw_data = utils.replace_cloudflare_emails(raw_data)
        table = utils.find_substring(raw_data, b'<table ', b'</table>')
        if not table:
            return []
        context = self.get_main_context(raw_data, url=url)

        node = utils.parse_html_fragment(table)[0]

        elems = []

        for elem in node.xpath('//tr')[1:]:
            elem = parse_talk_item(elem, context=context)
            if elem:
                elems.append(elem)
            else:
                logger.warning('Cannot parse talk item')

        return elems

    def get_favourited_talk_list(self, page=1, raw_data=None):
        """Возвращает список объектов :class:`~tabun_api.TalkItem` с избранными личными сообщениями."""
        url = "/talk/favourites/page{}/".format(int(page))
        if not raw_data:
            self.check_login()
            raw_data = self.urlread(url)

        raw_data = utils.replace_cloudflare_emails(raw_data)
        table = utils.find_substring(raw_data, b'<table ', b'</table>')
        if not table:
            return []
        context = self.get_main_context(raw_data, url=url)

        node = utils.parse_html_fragment(table)[0]

        elems = []

        for elem in node.xpath('//tr')[1:]:
            elem = parse_talk_item(elem, context=context)
            if elem:
                elems.append(elem)
            else:
                logger.warning('Cannot parse talk item')

        return elems

    def get_talk(self, talk_id, raw_data=None):
        """Возвращает объект :class:`~tabun_api.TalkItem` беседы с переданным номером."""
        url = "/talk/read/" + text(int(talk_id)) + "/"
        if not raw_data:
            self.check_login()
            raw_data = self.urlread(url)

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

        recipients = []
        recipients_inactive = []
        for x in item.xpath('div[@class="talk-search talk-recipients"]/header/a[@class!="link-dotted"]'):
            recipients.append(x.text.strip())
            if 'inactive' in x.get('class', ''):
                recipients_inactive.append(x.text.strip())

        footer = item.find("footer")
        author = footer.xpath('ul/li[@class="topic-info-author"]/a[2]/text()')[0].strip()
        date = footer.xpath('ul/li[@class="topic-info-date"]/time')[0]
        utctime = utils.parse_datetime(date.get("datetime"))
        date = time.strptime(date.get("datetime")[:-6], "%Y-%m-%dT%H:%M:%S")

        comments = self.get_comments(url, raw_data=raw_data)

        context = self.get_main_context(raw_data, url=url)
        context['favourited'] = bool(footer.xpath('ul/li[@class="topic-info-favourite"]/i[@class="favourite active"]'))
        context['last_is_incoming'] = None
        context['unread_comments_count'] = 0

        return TalkItem(
            talk_id, recipients, False, title, date,
            body, author, comments, utctime,
            recipients_inactive=recipients_inactive, comments_count=len(comments),
            context=context,
        )

    def delete_talk(self, talk_id):
        """Удаляет личное сообщение.

        :param int talk_id: ID удаляемого письма
        """

        self.check_login()
        resp = self.urlopen(
            url='/talk/delete/' + text(int(talk_id)) + '/?security_ls_key=' + self.security_ls_key,
            headers={"referer": (self.http_host or http_host) + "/talk/" + text(talk_id) + "/"},
            redir=False
        )
        if resp.getcode() // 100 != 3:
            raise TabunError('Cannot delete talk', code=resp.getcode())

    def get_activity(self, url='/stream/all/', raw_data=None):
        """Возвращает список последних событий."""
        if not raw_data:
            raw_data = self.urlread(url)

        raw_data = utils.find_substring(raw_data, b'<div id="content"', b'<!-- /content', with_end=False)
        if not raw_data:
            return []
        raw_data = utils.replace_cloudflare_emails(raw_data)
        node = utils.parse_html_fragment(raw_data)
        if not node:
            return []
        node = node[0]

        last_id = node.find('span')
        if last_id is not None and last_id.get('data-last-id'):
            # Табун
            last_id = int(last_id.get('data-last-id'))
        else:
            # Остальные LiveStreet
            last_id = node.find('input')
            if last_id is not None and last_id.get('id') == 'stream_last_id' and last_id.get('value'):
                last_id = int(last_id.get('value'))
            else:
                last_id = -1

        item = None
        items = []

        for li in node.find('ul').findall('li'):
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

        data = self.send_form_and_read("/stream/get_more_all/", fields)
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
        if (href.endswith('/created/topics') or href.endswith('/created/topics/')) and '/profile/' in href:
            # Есть такой баг: можно оценивать личные блоги
            blog = None
            data = href.split('/profile/', 1)[1]
            data = data[:data.find('/')]
        else:
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

    elif 'stream-item-type-add_wall' in classes:
        typ = ActivityItem.WALL_ADD
        data = item.xpath('span/a[2]/text()')[0]
        # TODO: comment content

    else:
        return

    username = item.xpath('p[@class="info"]/a/strong/text()[1]')[0]
    date = item.xpath('p[@class="info"]/span[@class="date"]')[0].get('title')
    if not date:
        return
    date = time.strptime(utils.mon2num(date), "%d %m %Y, %H:%M")
    return ActivityItem(typ, date, post_id, comment_id, blog, username, title, data)


def parse_post(item, context=None):
    # Парсинг поста. Не надо юзать эту функцию.
    header = item.find("header")
    title = header.find("h1")
    if title is None:
        return

    context = dict(context) if context else {}

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
    utctime = None
    if not post_time:
        post_time = item.xpath('header/div[@class="topic-info"]/time')  # mylittlebrony.ru
    if post_time:
        utctime = utils.parse_datetime(post_time[0].get("datetime"))
        post_time = time.strptime(post_time[0].get("datetime")[:-6], "%Y-%m-%dT%H:%M:%S")
    else:
        utctime = datetime.utcnow()
        post_time = time.localtime()

    body = item.xpath('div[@class="topic-content text"]')
    if len(body) == 0:
        return
    body = body[0]

    if body.get('data-escaped') == '1':
        # всё почищено в utils
        raw_body = body.text
        is_short = body.get('data-short') == '1'
        cut_text = body.get('data-short-text') or None
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
            cut_text = nextbtn[-1].text.strip() or None
            body.remove(nextbtn[-1])
        else:
            cut_text = None

        if len(body) > 0 and body[-1].tail:
            body[-1].tail = body[-1].tail.rstrip()
        elif len(body) == 0 and body.text:
            body.text = body.text.rstrip()

    footer = item.find("footer")
    ntags = footer.find("p")
    tags = []
    fav_tags = []
    if ntags is not None:
        for ntag in ntags.findall("a"):
            if ntag.text:
                tags.append(text(ntag.text))
        for fav_ntag_li in ntags.xpath('*[starts-with(@class, "topic-tags-user")]'):
            fav_ntag = fav_ntag_li.find('a')
            if fav_ntag is not None and fav_ntag.text:
                fav_tags.append({'tag': fav_ntag.get('href'), 'url': fav_ntag.text})

    tags_btn = ntags.xpath('span[starts-with(@class, "topic-tags-edit")]')
    can_save_favourite_tags = tags_btn and 'display:none' not in tags_btn[0].get('style', '') and 'display: none' not in tags_btn[0].get('style', '')

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

    votecls = header.xpath('div[@class="topic-info"]/div/div')
    if votecls:
        votecls = votecls[0].get('class', '').split()
        context['can_vote'] = 'not-voted' in votecls and 'vote-not-expired' in votecls and 'vote-nobuttons' not in votecls
        if 'voted-up' in votecls:
            context['vote_value'] = 1
        elif 'voted-down' in votecls:
            context['vote_value'] = -1
        elif 'voted-zero' in votecls:
            context['vote_value'] = 0
        else:
            context['vote_value'] = None
    else:
        votecls = None
        context['can_vote'] = None
        context['vote_value'] = None

    context['can_edit'] = bool(header.xpath('div[@class="topic-info"]//a[@class="actions-edit"]'))
    context['can_delete'] = bool(header.xpath('div[@class="topic-info"]//a[@class="actions-delete"]'))
    context['can_comment'] = None  # из <article/> не выяснить никак
    context['subscribed_to_comments'] = None

    context['unread_comments_count'] = comments_new_count
    context['favourited'] = favourited
    context['favourite_tags'] = fav_tags
    context['can_save_favourite_tags'] = can_save_favourite_tags

    return Post(
        post_time, blog, post_id, author, title, draft,
        vote_count, vote_total, body if raw_body is None else None, tags,
        comments_count, None, is_short, private, blog_name,
        poll, favourite, None, download, utctime, raw_body,
        cut_text, context=context
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


def parse_comment(node, post_id, blog=None, parent_id=None, context=None):
    # И это тоже парсинг коммента. Не надо юзать эту функцию.
    body = None
    context = dict(context) if context else {}
    try:
        info = node.xpath('ul[@class="comment-info"]')
        if not info:
            info = node.xpath('div[@class="comment-path"]/ul[@class="comment-info"]')
        info = info[0] if info else None
        if info is None:
            if 'comment-deleted' not in node.get("class", "") and 'comment-bad' not in node.get("class", ""):
                logger.warning('Comment in post %s (id=%s) has no info! Please report to andreymal.', post_id, node.get('id', 'N/A'))
            return

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
        utctime = utils.parse_datetime(tm)
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
        except (KeyboardInterrupt, SystemExit):
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

        vote = 0
        context['can_vote'] = None
        context['vote_value'] = None

        vote_area = info.xpath('li[starts-with(@id, "vote_area_comment")]')
        if vote_area:
            vote = vote_area[0].xpath('span[@class="vote-count"]/text()[1]')
            vote = int(vote[0].replace("+", ""))
            if vote_area[0].xpath('div[@class="vote-up"]'):  # проверка, что пост не из ленты (в ней классы полупустые)
                votecls = vote_area[0].get('class', '').split()
                # vote-expired стоит также у своих комментов, осторожно
                context['can_vote'] = 'voted' not in votecls and 'vote-expired' not in votecls
                if 'voted-up' in votecls:
                    context['vote_value'] = 1
                elif 'voted-down' in votecls:
                    context['vote_value'] = -1

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
        context['favourited'] = favourited

    except AttributeError:
        return
    except IndexError:
        return

    if body is not None:
        return Comment(tm, blog, post_id, comment_id, nick, body if raw_body is None else None, vote, parent_id,
                       post_title, unread, deleted, favourite, None, utctime, raw_body, context=context)


def parse_deleted_comment(node, post_id, blog=None, context=None):
    # И это тоже парсинг коммента! Но не простого, а удалённого.
    try:
        comment_id = int(node.get("id").rsplit("_", 1)[-1])
    except:
        return
    context = dict(context) if context else {}
    unread = "comment-new" in node.get("class", "")
    deleted = "comment-deleted" in node.get("class", "")
    bad = "comment-bad" in node.get("class", "")  # вроде обещалось, что это временно, поэтому пусть пока тут
    if not deleted and not bad:
        logger.warning('Deleted comment %s is not deleted! Please report to andreymal.', comment_id)
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
    return Comment(tm, blog, post_id, comment_id, nick, body, vote, parent_id, post_title, unread, deleted or bad, context=context)


def parse_talk_item(node, context=None):
    context = dict(context) if context else {}

    first_cell, recs, cell_title, info = node.findall("td")

    recipients = []
    recipients_inactive = []
    for a in recs.findall("a"):
        recipients.append(a.text.strip())
        if 'inactive' in a.get('class', ''):
            recipients_inactive.append(a.text.strip())

    talk_id = cell_title.find("a").get('href')[:-1]
    talk_id = int(talk_id[talk_id.rfind("/") + 1:])
    unread = bool(cell_title.xpath('a/strong'))

    title = cell_title.find("a").text_content()

    if 'cell-checkbox' in first_cell.get('class', ''):
        # Основной список — одна вёрстка
        date = time.strptime(utils.mon2num(info.text.strip()), '%d %m %Y')

        comments_count = cell_title.find('span')
        comments_count = int(comments_count.text.strip()) if comments_count is not None else 0

        unread_count = cell_title.xpath('span[@class="new"]')
        unread_count = int(unread_count[0].text[1:]) if unread_count else 0
        context['unread_comments_count'] = unread_count
        context['favourited'] = bool(info.xpath('a[@class="favourite active"]'))
        context['last_is_incoming'] = bool(cell_title.xpath('i[@class="icon-synio-arrow-left"]'))

    else:
        # Список избранного — совсем другая вёрстка

        date = time.strptime(utils.mon2num(info.text.strip()), '%d %m %Y, %H:%M')

        comments_count = cell_title.find('a').tail
        if comments_count:
            if '+' in comments_count:
                comments_count, unread_count = comments_count.split('+')
                comments_count = int(comments_count.strip())
                unread_count = int(unread_count.strip())
            else:
                comments_count = int(comments_count.strip() or 0)
                unread_count = 0
        else:
            comments_count = 0
            unread_count = 0

        context['unread_comments_count'] = unread_count
        context['favourited'] = None
        if 'cell-favourite' in first_cell.get('class', ''):
            context['favourited'] = bool(first_cell.xpath('a[@class="favourite active"]'))
        context['last_is_incoming'] = None

    return TalkItem(
        talk_id, recipients, unread, title, date,
        recipients_inactive=recipients_inactive,
        comments_count=comments_count,
        context=context,
    )


def parse_post_url(link):
    """Выдирает блог и номер поста из ссылки. Или возвращает (None, None), если выдрать не удалось."""
    if not link:
        return None, None
    m = post_url_regex.search(link)
    if not m:
        return None, None
    g = m.groups()
    return (g[1] if g[1] else None), int(g[2])
