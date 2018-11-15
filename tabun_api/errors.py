#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import warnings

from .compat import PY2, text


__all__ = ['TabunError', 'TabunResultError']


class TabunError(Exception):
    """Общее для библиотеки исключение.
    Содержит атрибут code с всякими разными циферками для разных типов исключения,
    обычно совпадает с HTTP-кодом ошибки при запросе.
    А в атрибуте ``message`` или текст, или снова код ошибки.

    Если возможно (например, при ошибке ввода-вывода), присутствует атрибут ``exc``
    с оригинальным исключением. Если это ``HTTPError``, то можно, например, вызвать
    ``exc.read()`` или ``user.saferead(exc)``.

    Для ошибки 404 в ``data`` содержатся первые 8192 байта ответа, которые нужно было
    прочитать библиотеке для своих нужд.
    """

    URL_ERROR = -50
    HTTP_ERROR = -40
    IO_ERROR = -30
    TIMEOUT = -20
    STATIC_404 = -404

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
