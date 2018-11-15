#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=redefined-builtin

from __future__ import unicode_literals

import warnings
from hashlib import md5

from . import utils
from .compat import PY2, text


__all__ = [
    'Post', 'Download', 'Comment', 'Blog', 'StreamItem', 'UserInfo',
    'Poll', 'TalkItem', 'ActivityItem',
]


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
        self.poll = poll or None
        self.favourite = int(favourite) if favourite is not None else None
        if download and (not isinstance(download, Download) or download.post_id != self.post_id):
            raise ValueError
        self.download = download
        self.utctime = utctime
        self.cut_text = text(cut_text) if cut_text else None
        self.context = context or {}

        self.body, self.raw_body = utils.normalize_body(body, raw_body, cls='topic-content text')

        if self.short != (self.cut_text is not None):
            utils.logger.warning('Post %d: self.short != (self.cut_text is not None)! If you don\'t use tabun_api.Post constructor directly, please report to andreymal.', post_id)

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
        """Считает md5-хэш от конкатенации полей поста (в utf-8), разделённых нулевым байтом.

        Поддерживаются только следующие поля:
        post_id, time (в UTC, в формате ``%Y-%m-%dT%H:%M:%SZ``), draft, author, blog, title,
        cut_text, body (как необработанный html), tags.

        По умолчанию используются все они. Если требуется одинаковость хэшей независимо
        от версии tabun_api, рекомендуется прописать список полей явно.

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

        # Not used: vote_count vote_total comments_count private blog_name poll favourite download context

        if fields is None or 'post_id' in fields:
            buf.append(text(self.post_id))

        if fields is None or 'time' in fields:
            buf.append(text(self.utctime.strftime('%Y-%m-%dT%H:%M:%SZ')))

        if fields is None or 'draft' in fields:
            buf.append('1' if self.draft else '0')

        for field in ('author', 'blog', 'title', 'cut_text'):
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
        host = self.context.get('http_host')
        if not host:
            raise ValueError('http_host is not available')
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
        self.post_id = int(post_id) if post_id is not None else None
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
            ("with body " if self.deleted and self.body is not None else "") +
            (((self.blog or '[personal]') + "/" + text(self.post_id) + "/") if self.post_id else "") +
            text(self.comment_id) + ">"
        )
        return o.encode('utf-8') if PY2 else o

    def hashsum(self, fields=None, debug=False):
        """Считает md5-хэш от конкатенации полей коммента (в utf-8), разделённых нулевым байтом.

        Поддерживаются только следующие поля:
        comment_id, time (в UTC, в формате ``%Y-%m-%dT%H:%M:%SZ``), author, body (как необработанный html).

        По умолчанию используются все они. Если требуется одинаковость хэшей независимо
        от версии tabun_api, рекомендуется прописать список полей явно.

        Аргумент ``fields`` — список полей для использования
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

    OPEN = 0
    CLOSED = 1
    HALFCLOSED = 2

    def __init__(self, blog_id, blog, name, creator, readers=0, rating=0.0, status=0,
                 description=None, admins=None, moderators=None, vote_count=-1, posts_count=-1,
                 created=None, avatar=None, raw_description=None, context=None, closed=None):
        self.blog_id = int(blog_id)
        self.blog = text(blog)
        self.name = text(name)
        self.creator = text(creator)
        self.readers = int(readers)
        self.rating = int(rating)
        self.status = int(status)
        self.admins = admins
        self.moderators = moderators
        self.vote_count = int(vote_count)
        self.posts_count = int(posts_count)
        self.created = created
        self.avatar = text(avatar) if avatar else None
        self.context = context or {}

        self.description, self.raw_description = utils.normalize_body(description, raw_description, cls='blog-content text')

        if closed is not None:
            warnings.warn('Blog(closed=...) is deprecated; use status instead of it', FutureWarning, stacklevel=2)
            self.status = self.CLOSED if closed else self.OPEN

    def __repr__(self):
        o = "<blog " + self.blog + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')

    @property
    def url(self):
        host = self.context.get('http_host')
        if not host:
            raise ValueError('http_host is not available')
        return host + '/blog/' + self.blog + '/'

    @property
    def closed(self):
        warnings.warn('blog.closed is deprecated; use blog.status instead of it', FutureWarning, stacklevel=2)
        return self.status != self.OPEN

    @closed.setter
    def closed(self, value):
        warnings.warn('blog.closed is deprecated; use blog.status instead of it', FutureWarning, stacklevel=2)
        self.status = self.CLOSED if value else self.OPEN


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
    """Информация о броняше.

    full=True, только если информация получена со страницы ``/profile/username/``.

    Словарь ``counts`` может быть пустым или содержать None или, если доступно,
    содержать следующие значения:

    * ``publications`` — число публикаций, учитываются посты, комментарии и
      (для своего профиля) заметки;
    * ``posts`` — число опубликованных постов (со страницы
      ``profile/username/created/topics или comments/``);
    * ``comments`` — число опубликованных комментариев (со страницы
      ``profile/username/created/topics или comments или notes/``);
    * ``notes`` — число заметок к пользователям (со страницы
      ``profile/username/created/topics или comments или notes/``);
    * ``favourites`` — число добавлений в избранное;
    * ``favourites_posts`` — число постов в избранном (со страницы
      ``profile/username/favourites/topics или comments/``);
    * ``favourites_comments`` — число комментариев в избранном (со страницы
      ``profile/username/favourites/topics или comments/``);
    * ``friends`` — число друзей.

    Дополнительные значения контекста:

    * ``note`` (строка или None) — заметка, оставленная текущим пользователем
    * ``can_edit_note`` (True/False/None) — можно ли редактировать заметку
      (определяется по наличию формы на странице /profile/foo/)
    * ``can_vote`` (True/False/None) — можно ли голосовать за пользователя (изменить рейтинг)
      (из-за багов лайвстрита корректно работает только на /profile/foo/)
    * ``vote_value`` (1/-1/None) — плюс (1), минус (-1) или голос ещё не оставлен (None)
      (из-за багов лайвстрита корректно работает только на /profile/foo/)
    """

    def __init__(self, user_id, username, realname, skill, rating, userpic=None, foto=None,
                 gender=None, birthday=None, registered=None, last_activity=None,
                 description=None, blogs=None, rating_vote_count=None, contacts=None,
                 counts=None, full=False, context=None, raw_description=None):
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

        self.rating_vote_count = rating_vote_count
        self.contacts = contacts
        self.counts = counts or {}
        self.full = bool(full)
        self.context = context or {}

    def __repr__(self):
        o = "<userinfo " + self.username + ">"
        return o.encode('utf-8') if PY2 else o

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__().decode('utf-8', 'replace')

    @property
    def url(self):
        host = self.context.get('http_host')
        if not host:
            raise ValueError('http_host is not available')
        return host + '/profile/' + self.username + '/'


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
