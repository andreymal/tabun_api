#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

import os
import re
import ssl
import time
import logging
import warnings
import threading
from hashlib import md5
from datetime import datetime
from socket import timeout as socket_timeout
from json import JSONDecoder

from . import errors, types, utils, compat
from .errors import TabunError, TabunResultError
from .types import Post, Download, Comment, Blog, StreamItem, UserInfo, Poll, TalkItem, ActivityItem
from .compat import PY2, BaseCookie, urequest, text_types, text, binary, html_unescape


__version__ = '0.7.8'

#: Адрес Табуна. Именно на указанный здесь адрес направляются запросы.
http_host = "https://tabun.everypony.ru"

#: Список полузакрытых блогов.
halfclosed = (
    "shipping", "RPG", "borderline", "ponymanie", "erpg", "tearsfromthemoon",
    "abode_Clan", "knifemanes", "zootopia",
)

#: Заголовки для HTTP-запросов. Возможно, стоит менять user-agent.
http_headers = {
    "connection": "close",
    "user-agent": "tabun_api/{} {}".format(__version__, utils.gen_user_agent()),
}

#: Регулярка для парсинга ссылки на пост.
post_url_regex = re.compile(r"/blog/(([A-z0-9_\-\.]{1,})/)?([0-9]{1,}).html")

#: Регулярка для парсинга прикреплённых файлов.
post_file_regex = re.compile(r'^Скачать \"(.+)" \(([0-9]*(\.[0-9]*)?) (Кб|Мб)\)$')


class NoRedirect(urequest.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp

    http_error_301 = http_error_303 = http_error_307 = http_error_302


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

    С помощью аргумента ``proxy`` можно задать используемый прокси-сервер. Это URL вида
    ``proto://username:password@hostname:port``. Поддерживаются протоколы socks4, socks5
    и http. Имя пользователя и пароль не обязательны, порт для SOCKS-прокси по умолчанию
    1080, так что адрес можно записать в кратком виде например так: ``socks5://myserver.com``

    Вместо передачи параметра можно установить переменную окружения
    ``TABUN_API_PROXY=socks5://myserver.com`` — конструктор её подхватит.
    Если нужно наоборот проигнорировать установленный ``TABUN_API_PROXY``,
    пропишите в аргументе ``proxy`` пустую строку (не None).

    По умолчанию все запросы направляются по адресу ``https://tabun.everypony.ru``. Если нужно
    парсить какой-то другой сайт (например, транк или локально запущенную копию Табуна),
    можно указать нужный адрес в опции ``http_host``.

    Если нужно добавить или переопределить какие-то HTTP-заголовки для конкретного объекта,
    можно запихнуть всё нужное в словарь ``override_headers``. При этом Cookie, Content-Type,
    X-Requested-With, Referer или ещё что-нибудь в любом случае затираются, если они нужны для
    отправки запроса (например, формы с созданием поста). Для установки дополнительных Cookie
    можно воспользоваться атрибутом ``extra_cookies``. Названия заголовков не чувствительны
    к регистру.

    Иногда CloudFlare внезапно хочет узнать, что клиент является нормальным браузером, и
    вместо Табуна присылает JavaScript-задачку. Здесь она автоматически решается при помощи
    `Js2Py <https://pypi.python.org/pypi/Js2Py>`_, если он установлен (``pip install Js2Py``).
    Вы можете прописать в конструкторе ``avoid_cf=False``, чтобы отключить решение задачки
    (в таком случае будут выпадать ошибки 503) или ``avoid_cf=True``, и в таком случае будет
    выкидываться исключение ``ImportError`` при отсутствующем Js2Py. Обход CloudFlare работает
    только при отправке запросов через методы :func:`~tabun_api.User.urlopen`
    или :func:`~tabun_api.User.urlread`.

    В ``ssl_params`` можно передать дополнительный параметр с настройками SSL. На данный момент
    параметр всего один — ``verify_mode``:

    * ``skip_all`` — не проверять SSL-сертификаты серверов вообще
    * ``skip_current_host`` — не проверять SSL-сертификат только того сервера, который прописан
      в ``http_host``
    * любое другое значение — проверять все SSL-сертификаты

    У класса также есть следующие поля:

    * ``username`` — имя пользователя или None
    * ``talk_unread`` — число непрочитанных личных сообщений (обновляется после ``update_userinfo``)
    * ``skill`` — силушка (после ``update_userinfo``)
    * ``rating`` — кармушка (после ``update_userinfo``)
    * ``timeout`` — таймаут ожидания ответа от сервера (для функции ``urlopen``, по умолчанию 20)
    * ``session_id``, ``security_ls_key``, ``key`` — ну вы поняли
    * ``session_cookie_name`` — название печеньки, в которую положить ``session_id``
      (по умолчанию TABUNSESSIONID)
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
    sleep_func = time.sleep
    opener = None
    noredir = None
    opener_nossl = None
    noredir_nossl = None

    def __init__(
        self, login=None, passwd=None, session_id=None, security_ls_key=None, key=None,
        proxy=None, http_host=None, session_cookie_name='TABUNSESSIONID', avoid_cf=None,
        ssl_params=None,
        phpsessid=None
    ):
        if phpsessid is not None:
            warnings.warn('phpsessid is deprecated; use session_id instead of it', FutureWarning, stacklevel=2)
            session_id = phpsessid

        self.http_host = text(http_host or globals()['http_host']).rstrip('/')
        self.session_cookie_name = text(session_cookie_name)

        self.extra_cookies = {}

        if avoid_cf is None:
            # None — опциональный обход CF, только если установлен js2py
            avoid_cf = utils.is_module_available('js2py')
        elif avoid_cf:
            if not utils.is_module_available('js2py'):
                raise ImportError("No module named 'js2py'")
        self.avoid_cf = bool(avoid_cf)

        self.jd = JSONDecoder()
        self.lock = threading.Lock()
        self.wait_lock = threading.Lock()

        self.configure_opener(proxy, ssl_params)

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
            resp = self.urlopen('/login/', redir=False)
            if resp.code // 100 == 3:
                resp = self.urlopen('/')
            data = self._netwrap(resp.read)  # LIVESTREET_SECURITY_KEY в конце страницы и нужен нам
            resp.close()

            cookies = utils.get_cookies_dict(resp.headers)
            if not self.session_id:
                self.session_id = cookies.get(self.session_cookie_name)
            if not self.key:
                self.key = cookies.get('key')

            self.update_userinfo(data)

            if self.security_ls_key == 'LIVESTREET_SECURITY_KEY':  # old security fix by Random
                self.security_ls_key = cookies.get('LIVESTREET_SECURITY_KEY')

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

    def __repr__(self):
        result = '<tabun_api.User http_host={!r} username={!r}>'.format(
            self.http_host,
            self.username,
        )
        if PY2:
            result = result.encode('utf-8')
        return result

    def configure_opener(self, proxy=None, ssl_params=None):
        ssl_params = ssl_params or {}
        handlers = []

        if proxy is None:
            proxy = os.getenv('TABUN_API_PROXY')

        if proxy and (not isinstance(proxy, (text, binary)) or proxy.count(',') == 2):
            # legacy
            warnings.warn('Comma-separated proxy value is deprecated; use "protocol://host:port" instead', FutureWarning, stacklevel=2)
            if isinstance(proxy, (text, binary)):
                proxy = text(proxy).split(',')
            proxy = '{0}://{1}:{2}'.format(*proxy)

        if proxy:
            # FIXME: а тут настройки SSL игнорируются
            # https://github.com/Anorov/PySocks/issues/36
            import socks
            from sockshandler import SocksiPyHandler

            if ssl_params:
                raise NotImplementedError('Proxy cannot be used with ssl_params (not implemented yet)')

            handlers.append(SocksiPyHandler(**utils.build_proxy_params(proxy)))
            self.proxy = proxy

        self.opener = urequest.build_opener(*handlers)
        self.noredir = urequest.build_opener(*(handlers + [NoRedirect]))

        # Если просят пропускать проверку SSL-сертификата сервера
        if ssl_params.get('verify_mode') in ('skip_all', 'skip_current_host'):
            ctx_sv = ssl.create_default_context()
            ctx_sv.check_hostname = False
            ctx_sv.verify_mode = ssl.CERT_NONE
            h_sv = urequest.HTTPSHandler(context=ctx_sv)

            self.opener_nossl = urequest.build_opener(*handlers + [h_sv])
            self.noredir_nossl = urequest.build_opener(*handlers + [h_sv, NoRedirect])
        self.ssl_params = ssl_params

    def update_security_ls_key(self, raw_data):
        """Выдирает security_ls_key из страницы. Вызывается из update_userinfo."""
        pos = raw_data.rfind(b"var LIVESTREET_SECURITY_KEY =")
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
                utils.logger.warning('update_userinfo received unknown data')
            return None

        node = utils.parse_html_fragment(userinfo)[0]
        dd_user = node.xpath('//*[@id="dropdown-user"]')
        if not dd_user:
            self.username = None
            self.talk_count = 0
            self.skill = None
            self.rating = None
            return None
        dd_user = dd_user[0]

        username = dd_user.xpath('a[2]/text()[1]')
        if username and username[0]:
            self.username = username[0]
        else:
            self.username = None
            self.talk_count = 0
            self.skill = None
            self.rating = None
            return None

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
        query += "&return-path=" + urequest.quote(return_path if return_path else self.http_host + "/")
        if self.security_ls_key:
            query += "&security_ls_key=" + urequest.quote(self.security_ls_key)

        resp = self.urlopen("/login/ajax-login", query, {
            "X-Requested-With": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded",
            "Referer": self.http_host + "/login/",
        })
        data = self.saferead(resp)
        if data.lstrip()[0] not in (b"{", 123):
            raise TabunResultError(data.decode("utf-8", "replace"))
        data = self.jd.decode(data.decode('utf-8'))
        if data.get('bStateError'):
            raise TabunResultError(data.get("sMsg", ""))
        self.username = login

        cookies = utils.get_cookies_dict(resp.headers)
        if 'key' in cookies:
            self.key = cookies.get('key')

    def check_login(self):
        """Генерирует исключение, если нет ``session_id`` или ``security_ls_key``."""
        if not self.session_id or not self.security_ls_key:
            raise TabunError("Not logged in")

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
            url = self.http_host + url
        context = {
            'http_host': self.http_host,
            'url': url,
            'username': None,
        }

        userinfo = utils.find_substring(raw_data, b'<div class="dropdown-user"', b"<nav", with_end=False)
        if userinfo:
            f = userinfo.find(b'class="username">')
            if f >= 0:
                username = userinfo[userinfo.find(b'>', f) + 1:userinfo.find(b'</', f)]
                context['username'] = username.decode('utf-8').strip()
        else:
            auth_panel = utils.find_substring(raw_data, b'<ul class="auth"', b'<nav', with_end=False)
            if not auth_panel or 'Войти'.encode('utf-8') not in auth_panel:
                utils.logger.warning('get_main_context received unknown userinfo')

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
                url = self.http_host + url
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
            cookiedict = {
                self.session_cookie_name: self.session_id,
                'key': self.key,
                'LIVESTREET_SECURITY_KEY': self.security_ls_key,
            }
        else:
            cookiedict = {}
        cookiedict.update(self.extra_cookies)
        cookie = '; '.join('{}={}'.format(k, v) for k, v in cookiedict.items())
        if cookie:
            request_headers['Cookie'] = cookie

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
        except urequest.HTTPError as exc:
            data = None
            if exc.getcode() == 404:
                data = self._netwrap(exc.read, 8192)
                if b'/__errors__/main.css' in data or b'//projects.everypony.ru/error/main.css' in data:
                    raise TabunError('Static 404', TabunError.STATIC_404, data=data)
            raise TabunError(code=exc.getcode(), exc=exc, data=data)
        except urequest.URLError as exc:
            raise TabunError(exc.reason, TabunError.URL_ERROR, exc=exc)
        except compat.HTTPException as exc:
            raise TabunError("HTTP error", TabunError.HTTP_ERROR, exc=exc)
        except socket_timeout as exc:
            raise TabunError("Timeout", TabunError.TIMEOUT, exc=exc)
        except IOError as exc:
            raise TabunError('IOError: ' + text(exc), TabunError.TIMEOUT, exc=exc)

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

            url = request.get_full_url()
            if isinstance(url, binary):
                url = url.decode('utf-8')

            opener = self.opener if redir else self.noredir

            # Иногда бывает надо пропускать проверку SSL-сертификата
            if self.opener_nossl and self.noredir_nossl:
                if self.ssl_params.get('verify_mode') == 'skip_all':
                    opener = self.opener_nossl if redir else self.noredir_nossl
                elif self.ssl_params.get('verify_mode') == 'skip_current_host':
                    if url == self.http_host or url.startswith(self.http_host + '/'):
                        opener = self.opener_nossl if redir else self.noredir_nossl

            return self._netwrap(opener.open, request, timeout=timeout, _lock=True)

        finally:
            if not nowait:
                self.wait_lock.release()

    def start_cf_avoiding(self, resp):
        import js2py

        data = self._netwrap(resp.read)

        # Загружаем печеньки CloudFlare
        self.extra_cookies.update(utils.get_cookies_dict(resp.headers))

        # Парсим форму, которую будем отправлять через 5 секунд
        form = utils.find_substring(
            data,
            b'<form id="challenge-form"',
            b'</form>',
            with_start=True,
            with_end=True,
        )
        if not form:
            return False
        form = utils.parse_html_fragment(form)[0]

        # Творим магию джаваскрипта, предварительно отцепив её от браузерных переменных
        # 0. В оригинале достаётся хост через DOM, мы же пихаем сами
        t = self.http_host
        if '://' in t:
            t = t.split('://', 1)[-1]
        t = t.strip('/').replace('"', '\\"').replace('\n', '\\n')

        # 1. Выковыриваем сам js-код
        f1 = data.find(b'var s,t,o,p,b,r,e,a,k,i,n,g,f')
        if f1 < 0:
            return
        f2 = data.find(b'.value = ', f1, f1 + 5000)
        if f2 < 0:
            return
        f2 = data.find(b';', f2 + 5, f2 + 5000)
        if f2 < 0:
            return
        jscode = data[f1:f2 + 1].decode('utf-8', 'replace')

        # 2. В оригинале ответ устанавливается в форму, но нам нужно его получить сюда
        f1 = jscode.rfind('.value =')
        f1 = jscode.rfind(';', 0, f1)
        f2 = jscode.find('=', f1, f1 + 5000)
        jscode = jscode[:f1 + 1] + ' ' + jscode[f2 + 1:]

        # 3. Подставляем загруженный выше хост вместо работы с DOM
        f1 = jscode.find(" = document.createElement('div')")
        f1 = jscode.rfind(';', 0, f1)
        f2 = jscode.find("('challenge-form');", f1 + 5)
        jscode = jscode[:f1 + 1] + 'var t = "' + t + '";' + jscode[f2 + 19:]

        # 4. Выполняем код и профит
        answer = js2py.eval_js(jscode)

        # Собираем ссылку для ответа
        url = form.get('action') + '?'
        for inp in form.findall('input'):
            url += urequest.quote(inp.get('name').encode('utf-8'))
            if inp.get('name') == 'jschl_answer':
                url += '=' + text(answer or '')
            elif inp.get('value'):
                url += '=' + urequest.quote(inp.get('value'))
            url += '&'
        url = url.rstrip('&')

        # CloudFlare требует ждать перед отправкой ответа; ждём
        self.sleep_func(4)

        # Отвечаем
        try:
            resp2 = self.urlopen(url, redir=False, avoid_cf=False)
        except TabunError as exc:
            if exc.code == 503:
                return False
            else:
                raise

        # В ответе CloudFlare просит поставить ещё печенек
        self.extra_cookies.update(utils.get_cookies_dict(resp2.headers))

        return resp2.code // 100 == 3


    def urlopen(self, url, data=None, headers=None, redir=True, nowait=False, with_cookies=True, timeout=None, avoid_cf=None):
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
        :param bool with_cookies: прикреплять ли session_id и остальные печеньки
          (отключайте для запросов не к Табуну) (печеньки из ``extra_cookies`` прикрепляются в любом случае)
        :param timeout: таймаут (по умолчанию ``user.timeout``)
        :type timeout: float или None
        :param bool avoid_cf: переопределяет значение поля ``avoid_cf`` (см. конструктор)
        :rtype: ``urllib.addinfourl`` / ``urllib.response.addinfourl``
        """
        if avoid_cf is None:
            avoid_cf = self.avoid_cf
        for i in range(10):
            try:
                req = self.build_request(url, data, headers, with_cookies)
                return self.send_request(req, redir, nowait, timeout)
            except TabunError as exc:
                if i >= 9 or not avoid_cf or exc.code != 503 or not isinstance(exc.exc, urequest.HTTPError) or not exc.exc.headers.get('CF-RAY'):
                    raise
                # Обход DDoS Protection от CloudFlare
                self.start_cf_avoiding(exc.exc)

    def urlread(self, url, data=None, headers=None, redir=True, nowait=False, with_cookies=True, timeout=None, avoid_cf=None):
        """Как ``return self.urlopen(*args, **kwargs).read()``, но с перехватом
        исключений, возникших в процессе чтения (см. :func:`~tabun_api.User.saferead`).
        """

        resp = self.urlopen(url, data, headers, redir, nowait, with_cookies, timeout, avoid_cf)
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
        fields = dict(fields or ())
        fields['security_ls_key'] = self.security_ls_key
        data = self.send_form_and_read(url, fields or {}, files, headers=headers)

        if data.lstrip().startswith(b'<textarea>{'):
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

    def add_post(self, blog_id, title, body, tags, *args, **kwargs):
        """Отправляет пост и возвращает имя блога с номером поста. Может кидаться
        исключением :class:`~tabun_api.TabunResultError` при невалидном посте.

        :param blog_id: ID блога, в который добавляется пост
        :type blog_id: int
        :param title: заголовок создаваемого поста
        :type title: строка
        :param body: текст поста
        :type body: строка
        :param tags: теги поста
        :type tags: строка или коллекция строк
        :param bool forbid_comment: закрыть (True) или открыть (False) написание комментариев
        :param bool draft: если True, то создание в черновиках вместо публикации
        :param bool check_if_error: проверяет наличие поста по заголовку даже в случае ошибки
          (если, например, таймаут или 404, но пост, как иногда бывает, добавляется)
        :returns: кортеж ``(blog, post_id)`` или ``(None, None)`` при неудаче
        """

        # tmp: forbid_comment=False, draft=False, check_if_error=False
        if args:
            if 'draft' not in kwargs:
                # Обратная совместимость такая обратная, эх-эх
                warnings.warn('Arguments of add_post and add_poll methods were changed; please use `draft=True/False` instead of positional argument', FutureWarning, stacklevel=2)

                forbid_comment = False
                draft = args[0]
                if len(args) == 2:
                    # args=(draft, check_if_error), kwargs={}
                    check_if_error = args[1]
                elif len(args) > 2:
                    raise TypeError
                else:
                    # args=(draft,), kwargs={check_if_error}
                    check_if_error = kwargs.get('check_if_error', False)
            else:
                if len(args) != 1:
                    raise TypeError
                forbid_comment = args[0]
                draft = kwargs.get('draft', False)
                check_if_error = kwargs.get('check_if_error', False)
        else:
            # args=(), kwargs={forbid_comment, draft, check_if_error}
            forbid_comment = kwargs.get('forbid_comment', False)
            draft = kwargs.get('draft', False)
            check_if_error = kwargs.get('check_if_error', False)

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
        if forbid_comment:
            fields['topic_forbid_comment'] = '1'

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
            except TabunError:
                posts = []
            posts.reverse()

            for post in posts[:2]:
                if post and post.title == text(title) and post.author == self.username:
                    return post.blog, post.post_id

            raise
        else:
            return parse_post_url(link)

    def add_poll(self, blog_id, title, choices, body, tags, *args, **kwargs):
        """Создает опрос и возвращает имя блога с номером поста. Может кидаться
        исключением :class:`~tabun_api.TabunResultError` при невалидном посте.

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
        :param bool forbid_comment: закрыть (True) или открыть (False) написание комментариев
        :param bool draft: если True, то создание в черновиках вместо публикации
        :param bool check_if_error: проверяет наличие поста по заголовку даже в случае ошибки
          (если, например, таймаут или 404, но пост, как иногда бывает, добавляется)
        :returns: кортеж ``(blog, post_id)`` или ``(None, None)`` при неудаче
        """

        # tmp: forbid_comment=False, draft=False, check_if_error=False
        if args:
            if 'draft' not in kwargs:
                # Обратная совместимость такая обратная, эх-эх
                warnings.warn('Arguments of add_post and add_poll methods were changed; please use `draft=True/False` instead of positional argument', FutureWarning, stacklevel=2)

                forbid_comment = False
                draft = args[0]
                if len(args) == 2:
                    # args=(draft, check_if_error), kwargs={}
                    check_if_error = args[1]
                elif len(args) > 2:
                    raise TypeError
                else:
                    # args=(draft,), kwargs={check_if_error}
                    check_if_error = kwargs.get('check_if_error', False)
            else:
                if len(args) != 1:
                    raise TypeError
                forbid_comment = args[0]
                draft = kwargs.get('draft', False)
                check_if_error = kwargs.get('check_if_error', False)
        else:
            # args=(), kwargs={forbid_comment, draft, check_if_error}
            forbid_comment = kwargs.get('forbid_comment', False)
            draft = kwargs.get('draft', False)
            check_if_error = kwargs.get('check_if_error', False)

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
        if forbid_comment:
            fields.append(('topic_forbid_comment', '1'))

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
            except TabunError:
                posts = []
            posts.reverse()

            for post in posts[:2]:
                if post and post.title == text(title) and post.author == self.username:
                    return post.blog, post.post_id

            raise
        else:
            return parse_post_url(link)

    def create_blog(self, title, url, description, rating_limit=0, status=0, closed=None):
        """Создаёт блог и возвращает его url-имя или None в случае неудачи.

        :param title: заголовок нового блога
        :type title: строка
        :param url: url-имя блога (на латинице без пробелов)
        :type url: строка
        :param description: описание блога (допустим HTML-код)
        :type description: строка
        :param int rating_limit: минимальный рейтинг пользователя, при котором можно писать в блог
        :param int status: 0 - открытый блог, 1 - закрытый
        :rtype: строка или None
        """

        if closed is not None:
            warnings.warn('create_blog(closed=...) is deprecated; use status instead of it', FutureWarning, stacklevel=2)
            status = Blog.CLOSED if closed else Blog.OPEN

        if status == 0:
            blog_type = 'open'
        elif status == 1:
            blog_type = 'close'
        else:
            raise ValueError('Unsupported blog status: {!r}'.format(status))

        self.check_login()

        fields = {
            'security_ls_key': self.security_ls_key,
            "blog_title": text(title),
            "blog_url": text(url),
            "blog_type": blog_type,
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

    def edit_blog(self, blog_id, title, description, rating_limit=0, status=0, closed=False):
        """Редактирует блог и возвращает его url-имя или None в случае неудачи.

        :param int blog_id: ID блога, который редактируется
        :param title: заголовок блога
        :type title: строка
        :param description: описание блога (допустим HTML-код)
        :type description: строка
        :param int rating_limit: минимальный рейтинг пользователя, при котором можно писать в блог
        :param int status: 0 - открытый блог, 1 - закрытый
        :rtype: строка или None
        """

        if closed is not None:
            warnings.warn('create_blog(closed=...) is deprecated; use status instead of it', FutureWarning, stacklevel=2)
            status = Blog.CLOSED if closed else Blog.OPEN

        if status == 0:
            blog_type = 'open'
        elif status == 1:
            blog_type = 'close'
        else:
            raise ValueError('Unsupported blog status: {!r}'.format(status))

        self.check_login()

        fields = {
            'security_ls_key': self.security_ls_key,
            "blog_title": text(title),
            "blog_url": "",
            "blog_type": blog_type,
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
            headers={"referer": self.http_host + "/"},
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
        if data == b'Hacking attemp!':
            raise TabunResultError('Hacking attemp!')
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
            headers={"referer": self.http_host + "/blog/" + text(post_id) + ".html"},
            redir=False
        )
        if resp.getcode() // 100 != 3:
            raise TabunError('Cannot delete post', code=resp.getcode())

    def preview_comment(self, body, fix=False, save=False):
        """Возвращает HTML-код предпросмотра комментария.

        :param body: текст комментария
        :type body: строка
        :param bool fix: если False, то предпросмотр для создания комментария,
          если True, то для редактирования
        :param bool save: неизвестно
        :rtype: строка
        """

        self.check_login()

        fields = {
            'security_ls_key': self.security_ls_key,
            'text': text(body),
            'fix': '1' if fix else '0',
            'save': '1' if save else '0',
        }

        data = self.ajax('/ajax/preview/text/', fields, ())
        return data['sText']

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

    def get_pagination(self, raw_data):
        """Возвращает со страницы номер текущей страницы и список с номерами страниц
        и текстами ссылок (кортеж из номера и строки), которые содержатся в элементе
        с пагинацией (``<div class="pagination">``).
        Соответственно, первый элемент списка — номер первой страницы, последний —
        последней страницы. Номера могут повторяться, если так в коде страницы.
        Если пагинаций ноль или больше одного, возвращается ``(None, None)``.

        :param bytes raw_data: код страницы
        :rtype: ``(int, list)``
        """

        assert isinstance(raw_data, binary)
        f = raw_data.find(b'<div class="pagination">')
        if f < 0:
            return None, None

        f2 = raw_data.find(b'<div class="pagination">', f + 2)
        if f2 >= 0:
            utils.logger.warning('Multiple paginations on page! If it is not tabun bug, please report to andreymal.')
            return None, None

        f = raw_data.find(b'<ul>', f + 2, f + 1500)
        f = raw_data.find(b'<ul>', f + 2, f + 1500)  # Выдираем второй список
        f2 = raw_data.find(b'</ul>', f + 2, f + 1500)

        ul = utils.parse_html_fragment(raw_data[f:f2 + 5])[0]

        pages = []
        current_page = None

        for li in ul.findall('li'):
            a = li.find('a')
            txt = li.text_content().strip()

            href = a.get('href', '') if a is not None else None
            if href and '?' in href:
                href = href[:href.find('?')]
            elif href and '#' in href:
                href = href[:href.find('#')]

            if href:
                page = href.rstrip('/').rsplit('/page', 1)[-1]
                if page.isdigit():
                    page = int(page)
                else:
                    assert txt == 'первая'
                    page = 1
            else:
                page = int(txt)

            pages.append((page, txt))

            if li.get('class', '') == 'active':
                assert current_page is None
                current_page = page

        assert current_page is not None
        return current_page, pages

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

        if url.startswith('/'):
            url = self.http_host + url

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
                post = parse_rss_post(item, context={'http_host': self.http_host, 'username': self.username, 'url': url})
                if post:
                    posts.append(post)

            return posts

        context = self.get_main_context(raw_data, url=url)

        data = utils.find_substring(raw_data, b"<article ", b"</article> <!-- /.topic -->", extend=True)
        if not data:
            raise TabunError("No post")

        can_be_short = not url.split('?', 1)[0].endswith('.html')
        escaped_data = utils.escape_topic_contents(data, can_be_short)
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

        # Вытаскиваем базовую информацию о комментариях
        # (манипулируем строками вместо парсинга через lxml, чтобы не тратиться
        # на парсинг ненужных нам элементов)
        comments_pos = raw_data.find(b'<div class="comments')
        if comments_pos < 0:
            comments_pos = raw_data.find(b'<div id="comments"')

        comments_header_end = -1
        if comments_pos > 0:
            comments_header_end = raw_data.find(b'</header>', comments_pos, comments_pos + 5000)

        if comments_header_end >= 0:
            # А вот уже теперь парсим только нужные элементы
            comments_info_node = utils.parse_html_fragment(raw_data[comments_pos:comments_header_end + 9])[0]
            post.comments_count = int(comments_info_node.xpath('.//*[@id="count-comments"][1]/text()[1]')[0].strip())
            post.context['unread_comments_count'] = 0
            post.context['subscribed_to_comments'] = comments_info_node.xpath('.//input[@id="comment_subscribe"][1]')[0].get("checked") == 'checked'
        else:
            post.comments_count = None

        post.context['can_comment'] = b'<h4 class="reply-header" id="comment_id_0">' in raw_data

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
            f = raw_data.find(b'<div class="comments')
            if raw_data.rstrip().endswith(b'<a href="') and f >= 0 and b'<li class="comment-link">' in raw_data[-100:]:
                # После удаления блога с комментами ломается лента, обходим
                data = raw_data[f:]
            else:
                return {}
        data = utils.replace_cloudflare_emails(data)
        escaped_data = utils.escape_comment_contents(utils.escape_topic_contents(data, True))
        div = utils.parse_html_fragment(escaped_data)
        if not div:
            return {}
        div = div[0]

        raw_comms = []

        for node in div.findall("div"):
            if 'comment-wrapper' in node.get('class', '').split():
                raw_comms.extend(parse_wrapper(node))

        # for /comments/ page
        for sect in div.findall("section"):
            if "comment" in sect.get('class', '').split():
                raw_comms.append(sect)

        comms = {}
        context = self.get_main_context(raw_data, url=url)

        for sect in raw_comms:
            c = parse_comment(sect, post_id, blog, context=context)
            if c is not None:
                # Нормальный комментарий
                comms[c.comment_id] = c
            else:
                # Удалённый или скрытый комментарий
                if sect.get("id", "").find("comment_id_") == 0:
                    c = parse_deleted_comment(sect, post_id, blog, context=context)
                    if c is not None:
                        comms[c.comment_id] = c
                    else:
                        utils.logger.warning('Cannot parse deleted comment %s (url: %s)', sect.get('id'), url)
                else:
                    # TODO: нужно ли на новом Табуне?
                    tmp = sect.xpath('.//ul[@class="comment-info"]/li[starts-with(@id, "vote_area_comment")]')
                    if tmp:
                        utils.logger.warning('Unknown comment format %s, it can be comment from deleted blog; skipped (url: %s)', tmp[0].get('id'), url)
                    else:
                        utils.logger.warning('Unknown comment format %s (url: %s)', sect.get('id'), url)

        return comms

    def get_blogs_list(self, page=1, order_by="blog_rating", order_way="desc", url=None):
        """Возвращает список объектов Blog."""
        if not url:
            url = "/blogs/" + (("page" + text(page) + "/") if page > 1 else "")
            url += "?order=" + text(order_by)
            url += "&order_way=" + text(order_way)

        raw_data = self.urlread(url)
        data = utils.find_substring(raw_data, b'<table class="table table-blogs', b'</table>')
        node = utils.parse_html_fragment(data)
        if not node:
            return []
        node = node[0]
        if node.find("tbody") is not None:
            node = node.find("tbody")

        context = self.get_main_context(raw_data, url=url)

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

            if not closed:
                blog_status = Blog.OPEN
            elif blog in halfclosed:
                blog_status = Blog.HALFCLOSED
            else:
                blog_status = Blog.CLOSED

            blogs.append(Blog(blog_id, blog, name, creator, readers, rating, blog_status, context=dict(context)))

        return blogs

    def get_blog(self, blog, raw_data=None):
        """Возвращает информацию о блоге. Функция не доделана."""
        blog = text(blog)
        url = "/blog/" + text(blog) + "/"
        if not raw_data:
            raw_data = self.urlread(url)
        raw_data = utils.escape_blog_content(raw_data)
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
        if not closed:
            blog_status = Blog.OPEN
        elif blog in halfclosed:
            blog_status = Blog.HALFCLOSED
        else:
            blog_status = Blog.CLOSED

        vote_item = blog_top.xpath('.//span[@class="vote-count"]')
        if vote_item:
            # Новый Табун
            vote_item = vote_item[0]
            vote_count = int(vote_item.get("title", "0").rsplit(" ", 1)[-1])
            blog_id = int(vote_item.get('id').rsplit('_', 1)[-1])
            vote_total = float(vote_item.text_content().strip().replace('+', ''))
        else:
            # Старый Табун
            vote_item = blog_top.xpath('div/div[@class="vote-item vote-count"]')[0]
            vote_count = int(vote_item.get("title", "0").rsplit(" ", 1)[-1])
            blog_id = int(vote_item.find("span").get("id").rsplit("_", 1)[-1])
            vote_total = float(vote_item.find("span").text_content().strip().replace('+', ''))

        avatar = blog_inner.xpath("header/img")[0].get("src")

        content = blog_inner.find("div")
        info = content.find("ul")

        description = content.find("div")
        if description is not None and description.get('data-escaped') == '1':
            raw_description = description.text
        else:
            raw_description = None
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

        return Blog(
            blog_id, blog, name, creator, readers, vote_total, blog_status,
            description if description is not None and raw_description is None else None,
            admins, moderators, vote_count, posts_count, created,
            avatar=avatar, raw_description=raw_description,
            context=self.get_main_context(raw_data, url=url),
        )

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

        post = self.get_post(post_id, blog, raw_data=raw_data)
        comments = self.get_comments(url=url, raw_data=raw_data)

        return post, comments

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

        url = self.http_host + "/" + (typ if typ in ("blog", "talk") else "blog") + "/ajaxresponsecomment/"

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

        context = {
            'http_host': self.http_host,
            'url': url,
            'username': self.username,  # вроде бы эта функция всё равно недоступна для незарегистрированных
        }

        comms = {}
        # comments/pid для Табуна, aComments/idParent для остальных LiveStreet
        # (При отсутствии комментариев в comments почему-то возвращается список вместо словаря)
        comms_list = data['comments'].values() if data.get('comments') else data['aComments']
        for comm in comms_list:
            node = utils.parse_html_fragment(utils.escape_comment_contents(comm['html'].encode('utf-8')))
            sect = node[0]
            post_id = target_id if typ == 'blog' else None
            parent_id = comm['pid'] if 'pid' in comm else comm['idParent']

            pcomm = parse_comment(sect, post_id, None, parent_id, context=context)

            if pcomm:
                comms[pcomm.comment_id] = pcomm
            else:
                if sect.get("id", "").find("comment_id_") == 0:
                    pcomm = parse_deleted_comment(sect, post_id, None, parent_id, context=context)
                    if pcomm:
                        comms[pcomm.comment_id] = pcomm
                    else:
                        utils.logger.warning('Cannot parse deleted ajax comment %s (url: %s)', sect.get('id'), url)
                else:
                    utils.logger.warning('Unknown ajax comment format %s (url: %s)', sect.get('id'), url)

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
        url = self.http_host + '/ajax/stream/topic/'
        data = self.ajax(url)
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
                context={'http_host': self.http_host, 'url': url, 'username': self.username}
            ))

        return items

    def get_short_blogs_list(self, raw_data=None):
        """Возвращает пустой список. После обновления Табуна не работает, функция оставлена для обратной совместимости.
        """
        return []

    def get_people_list(self, page=1, order_by="user_rating", order_way="desc", url=None, raw_data=None):
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

        if not raw_data:
            raw_data = self.urlread(url)
        data = utils.find_substring(raw_data, b'<table class="table table-users', b'</table>')
        if not data:
            return []
        node = utils.parse_html_fragment(data)
        if not node:
            return []
        node = node[0]
        if node.find("tbody") is not None:
            node = node.find("tbody")

        peoples = []
        base_context = self.get_main_context(raw_data, url=url)
        base_context['can_vote'] = None
        base_context['vote_value'] = None

        for tr in node.findall("tr"):
            context = base_context.copy()

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

            btns = tr.xpath('td/button')
            note = None
            for btn in btns:
                if 'button-action-note' in btn.get('class'):
                    note = btn
                    break
            if note is not None:
                context['note'] = note.get('title') or None
                if context['note']:
                    # Лайвстрит перестарался с экранированием
                    context['note'] = html_unescape(context['note']).strip()
            else:
                context['note'] = None
            context['can_edit_note'] = None

            peoples.append(UserInfo(
                utils.parse_avatar_url(userpic[0])[0] or -1, username[0], realname,
                skill[0], rating[0], userpic=userpic[0], full=False,
                context=context,
            ))

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

        raw_data = utils.escape_profile_content(raw_data)

        data = utils.find_substring(raw_data, b'<div id="content"', b'<!-- /content ', extend=True, with_end=False)
        if not data:
            return
        data = utils.replace_cloudflare_emails(data)
        node = utils.parse_html_fragment(data)
        if not node:
            return
        node = node[0]

        context = self.get_main_context(raw_data, url=url)

        # Блок в самом верху всех страниц профиля
        profile = node.xpath('div[@class="profile"]')[0]

        username = profile.xpath('h2[@itemprop="nickname"]/text()')[0]
        realname = profile.xpath('p[@class="user-name"]/text()')

        skill = float(profile.xpath('div[@class="strength"]/div[1]/text()')[0])

        vote_area = profile.xpath('div[@class="vote-profile"]/div[1]')[0]
        user_id = int(vote_area.get("id").rsplit("_")[-1])

        rating = float(profile.xpath('.//span[@id="vote_total_user_{}"]/text()'.format(user_id))[0].strip().replace('+', ''))
        rating_vote_count = profile.xpath('div[@class="vote-profile"]/div[@class="vote-label"]')[0]
        rating_vote_count = int(rating_vote_count.text.strip().rsplit(': ', 1)[-1])

        classes = tuple(vote_area.get('class', '').split())
        context['can_vote'] = 'not-voted' in classes and 'vote-nobuttons' not in classes
        if 'voted-up' in classes:
            context['vote_value'] = 1
        elif 'voted-down' in classes:
            context['vote_value'] = -1
        else:
            context['vote_value'] = None

        full = True

        # Блок с основной информацией на странице /profile/xxx/
        userpic = None
        description = None
        raw_description = None

        about = node.xpath('div[@class="profile-info-about"]')
        if about:
            about = about[0]
            userpic = about.xpath('a[1]/img')[0].get('src')
            description = about.xpath('div[@class="text"]')
            if description and description[0].get('data-escaped') == '1':
                raw_description = description[0].text
        else:
            about = None
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
            utils.logger.warning('Profile %s: registered date is None! Please report to andreymal.', username)
            registered = time.gmtime(0)
            description = []

        # Блок с контактами
        profile_right = node.xpath('div[@class="wrapper"]/div[@class="profile-right"]')

        if profile_right:
            contacts = []
            for ul in profile_right[0].xpath('ul[@class="profile-contact-list"]'):
                for li in ul.findall('li'):
                    icon = li.find('i')
                    a = li.find('a')
                    label = a.text.strip() if a is not None else li.text_content().strip()
                    ctype = icon.get('title', '') if icon is not None else ''

                    if ctype not in ('phone', 'mail', 'skype', 'icq', 'www', 'twitter', 'facebook', 'vkontakte', 'odnoklassniki'):
                        utils.logger.warning('Unknown contact type: %s', ctype)

                    contacts.append((
                        ctype,
                        a.get('href', '') if a is not None else None,
                        label,
                    ))
        else:
            contacts = None

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

        counts = {
            'publications': None,
            'posts': None,
            'comments': None,
            'favourites': None,
            'favourites_posts': None,
            'favourites_comments': None,
            'friends': None,
            'notes': None,
        }

        current_page = None

        # Получаем основные счётчики (публикации, избранные, друзья)
        for li in sidebar.xpath('section/ul[@class="nav nav-profile"]/li'):
            link = li.find('a').get('href', '')
            li_data = li.find('a').text.strip()
            value = utils.find_substring(li_data, ' (', ')', with_start=False, with_end=False)
            value = int(value) if value and value.isdigit() else 0

            if link.endswith('/created/topics/'):
                counts['publications'] = value
                if li.get('class') == 'active':
                    current_page = 'publications'

            elif link.endswith('/favourites/topics/'):
                counts['favourites'] = value
                if li.get('class') == 'active':
                    current_page = 'favourites'

            elif link.endswith('/friends/') and not link.endswith('/profile/friends/'):  # ну а вдруг
                counts['friends'] = value
                if li.get('class') == 'active':
                    current_page = 'friends'

            elif li_data == 'Информация' and li.get('class') == 'active':
                current_page = 'profile'

        # Получаем более детальные счётчики, если страница позволяет
        if current_page in ('publications', 'favourites'):
            nav_profile = utils.find_substring(raw_data, b'<ul class="nav nav-pills nav-pills-profile">', b'</ul>')
            if nav_profile:
                nav_profile = utils.parse_html_fragment(nav_profile)[0]
                tmp_posts = None
                tmp_comments = None
                tmp_notes = None

                for li in nav_profile.findall('li'):
                    link = li.find('a').get('href', '')
                    li_data = li.find('a').text.strip()
                    value = utils.find_substring(li_data, ' (', ')', with_start=False, with_end=False)
                    value = int(value) if value and value.isdigit() else 0

                    if link.endswith('/topics/'):
                        tmp_posts = value
                    elif link.endswith('/comments/'):
                        tmp_comments = value
                    elif link.endswith('/notes/'):
                        tmp_notes = value

                if current_page == 'favourites':
                    counts['favourites_posts'] = tmp_posts
                    counts['favourites_comments'] = tmp_comments
                    assert tmp_notes is None
                else:
                    counts['posts'] = tmp_posts
                    counts['comments'] = tmp_comments
                    counts['notes'] = tmp_notes

        # Заметка
        note_elem = sidebar.xpath('//p[@id="usernote-note-text"]')
        if note_elem:
            context['note'] = note_elem[0].text.strip() or None
            context['can_edit_note'] = True
        else:
            context['note'] = None
            context['can_edit_note'] = False  # На своей собственной учётке, например

        return UserInfo(
            user_id, username, realname[0] if realname else None, skill,
            rating, userpic, foto, gender, birthday, registered, last_activity,
            description[0] if description and raw_description is None else None, blogs,
            rating_vote_count=rating_vote_count, contacts=contacts,
            counts=counts, full=full, context=context,
            raw_description=raw_description,
        )

    def get_notes(self, page=1, url=None, raw_data=None):
        """Получает заметки, установленные текущим пользователем — список
        из словарей с ключами ``username``, ``note`` и ``date``.

        :param int page: страница
        :param url: ссылка на страницу, с которой достать заметки (при наличии page игнорируется)
        :type url: строка
        :param bytes raw_data: код страницы (чтобы не скачивать его по ссылке)
        """

        if not self.username:
            raise TabunError('Not logged in')

        if not url:
            url = '/profile/' + urequest.quote(text(self.username).encode('utf-8')) + '/created/notes/page' + str(int(page)) + '/'

        if not raw_data:
            raw_data = self.urlread(url)

        table = utils.find_substring(raw_data, b'<table class="table table-profile-notes"', b'</table>')
        if not table:
            return []

        result = []
        table = utils.parse_html_fragment(table)[0]
        for tr in table.findall('tr'):
            username = tr.xpath('td[@class="cell-username"]/a/text()[1]')
            if not username:
                continue
            username = username[0]

            note = tr.xpath('td[@class="cell-note"]/text()[1]')
            if not note:
                continue
            note = note[0].strip()

            date = tr.xpath('td[@class="cell-date"]/text()[1]')
            if not date:
                continue
            date = time.strptime(utils.mon2num(date[0].strip()), '%d %m %Y')

            result.append({
                'username': username,
                'note': note,
                'date': date
            })
        return result

    def save_note(self, user_id, note):
        """Меняет заметку у пользователя.

        :param int user_id: ID пользователя, которому пишем заметку
        :param note: Собственно заметка
        :type note: строка
        :return: установленная заметка (с учётом фильтрации html-тегов)
        :rtype: строка
        """

        fields = {
            'iUserId': text(int(user_id)),
            'text': text(note or ''),
        }

        data = self.ajax('/profile/ajax-note-save/', fields)
        return html_unescape(data['sText'])

    def remove_note(self, user_id):
        """Удаляет заметку у пользователя.

        :param int user_id: ID пользователя, у которого удаляем заметку
        """

        fields = {
            'iUserId': text(int(user_id)),
        }

        self.ajax('/profile/ajax-note-remove/', fields)

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

    def edit_comment(self, comment_id, body, set_lock=False):
        """Редактирует комментарий и возвращает кортеж из трёх строк: новый
        (или старый, если изменений нет) html-код комментария, сообщение
        с информацией для пользователя и некий ``notice``. В исключении
        :class:`~tabun_api.TabunResultError` в словаре `data` доступно поле
        ``newText``, тоже содержащее тело комментария даже в случае ошибки.

        :param int comment_id: ID комментария, который редактируем
        :param body: новый текст комментария
        :type body: строка
        :param bool set_lock: заблокировать дальнейшее изменение
        :rtype: (строка, строка или None, строка или None)
        """

        fields = {
            'idComment': int(comment_id),
            'newText': body.encode('utf-8'),
            'setLock': '1' if set_lock else '0',
        }

        data = self.ajax('/ajax/comment/edit/', fields)
        return (
            data['newText'],
            data.get('sMsg', None),
            data.get('notice', None),
        )

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

    def edit_post(self, post_id, blog_id, title, body, tags, forbid_comment=False, draft=False, check_if_error=False):
        """Редактирует пост и возвращает его блог и номер. Может кидаться
        исключением :class:`~tabun_api.TabunResultError` при невалидном посте.

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
        :param bool check_if_error: проверяет наличие поста по заголовку даже в случае ошибки
          (если, например, таймаут или 404, но пост, как иногда бывает, добавляется). Учтите, что
          в отличие от ``add_post`` здесь при проверке будет загружен сам пост, что может привести
          к слёту подсветки новых комментариев
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

        try:
            result = self.send_form('/topic/edit/' + text(int(post_id)) + '/', fields, redir=False)
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

            try:
                post = self.get_post(int(post_id))
            except TabunError:
                post = None

            if post and post.title == text(title) and post.author == self.username:
                return post.blog, post.post_id

            raise
        else:
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
                utils.logger.warning('Cannot parse talk item')

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
                utils.logger.warning('Cannot parse talk item')

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
        item = utils.parse_html_fragment(utils.escape_topic_contents(data, False))[0]

        header = item.find("header")
        title = header.find("h1").text
        author = header.xpath('.//a[@rel="author"]/text()[1]')[0].strip()

        body = item.xpath('div[@class="topic-content text"]')
        if len(body) == 0:
            return
        body = body[0]

        if body.get('data-escaped') == '1':
            # всё экранировано в utils.escape_topic_contents
            raw_body = body.text
        else:
            raw_body = None

        recipients = []
        recipients_inactive = []
        for x in item.xpath('div[@class="talk-search talk-recipients"]//a[contains(@class, "username")]'):
            recipients.append(x.text.strip())
            if 'inactive' in x.get('class', ''):
                recipients_inactive.append(x.text.strip())

        footer = item.find("footer")
        date_node = footer.xpath('ul/li[@class="topic-info-date"]/time')[0]
        utctime = utils.parse_datetime(date_node.get("datetime"))
        date = time.strptime(date_node.get("datetime")[:-6], "%Y-%m-%dT%H:%M:%S")  # legacy

        comments = self.get_comments(url, raw_data=raw_data)

        context = self.get_main_context(raw_data, url=url)
        context['favourited'] = bool(footer.xpath('ul/li[@class="topic-info-favourite"]/i[@class="favourite active"]'))
        context['last_is_incoming'] = None
        context['unread_comments_count'] = 0

        return TalkItem(
            talk_id, recipients, False, title, date,
            body if raw_body is None else None, author, comments, utctime,
            recipients_inactive=recipients_inactive, comments_count=len(comments),
            context=context,
            raw_body=raw_body,
        )

    def delete_talk(self, talk_id):
        """Удаляет личное сообщение.

        :param int talk_id: ID удаляемого письма
        """

        self.check_login()
        resp = self.urlopen(
            url='/talk/delete/' + text(int(talk_id)) + '/?security_ls_key=' + self.security_ls_key,
            headers={"referer": self.http_host + "/talk/" + text(talk_id) + "/"},
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
        title = item.xpath('a[2]')[0].text or ''

    elif 'stream-item-type-add_comment' in classes:
        typ = ActivityItem.COMMENT_ADD
        href = item.xpath('a[2]')[0].get('href')
        blog, post_id = parse_post_url(href)
        comment_id = int(href[href.rfind("#comment") + 8:])
        data = item.xpath('div/text()')
        data = data[0] if data else None
        title = item.xpath('a[2]')[0].text or ''

    elif 'stream-item-type-add_blog' in classes:
        typ = ActivityItem.BLOG_ADD
        href = item.xpath('a[2]')[0].get('href')[:-1]
        blog = href[href.rfind('/') + 1:]
        title = item.xpath('a[2]')[0].text or ''

    elif 'stream-item-type-vote_topic' in classes:
        typ = ActivityItem.POST_VOTE
        href = item.xpath('a[2]')[0].get('href')
        blog, post_id = parse_post_url(href)
        title = item.xpath('a[2]')[0].text or ''

    elif 'stream-item-type-vote_comment' in classes:
        typ = ActivityItem.COMMENT_VOTE
        href = item.xpath('a[2]')[0].get('href')
        blog, post_id = parse_post_url(href)
        comment_id = int(href[href.rfind("#comment") + 8:])
        title = item.xpath('a[2]')[0].text or ''

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
        title = item.xpath('a[2]')[0].text or ''

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
        title = item.xpath('a[2]')[0].text or ''

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
        # TODO: перепроверить, актуально ли для нового Табуна
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
                fav_tags.append({'url': fav_ntag.get('href'), 'tag': fav_ntag.text})

    tags_btn = ntags.xpath('span[starts-with(@class, "topic-tags-edit")]')
    can_save_favourite_tags = tags_btn and 'display:none' not in tags_btn[0].get('style', '') and 'display: none' not in tags_btn[0].get('style', '')

    draft = bool(header.xpath('h1/i[@class="icon-synio-topic-draft"]'))

    rateelem = header.xpath('div[@class="topic-info"]//*[@class="vote-item vote-count"][1]')
    if rateelem:
        rateelem = rateelem[0]

        vote_count = int(rateelem.get("title").rsplit(" ", 1)[-1])

        try:
            vote_total = int((rateelem.text or "").strip().lstrip("+"))
        except ValueError:
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
        favourited = bool(fav.xpath('*[@class="favourite active"]'))
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


def parse_rss_post(item, context=None):
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

    return Post(post_time, blog, post_id, author, title, False, 0, 0, node, tags, short=len(nextbtn) > 0, private=private, context=context)


def parse_wrapper(node):
    # Парсинг коммента. Не надо юзать эту функцию.
    comms = []
    nodes = [node]
    while nodes:
        node = nodes.pop(0)
        sect = node.find("section")
        if not sect.get('class'):
            break
        if 'comment' not in sect.get('class', '').split():
            break
        comms.append(sect)
        for node2 in node.findall('div'):
            if 'comment-wrapper' in node2.get('class', '').split():
                nodes.append(node2)
    return comms


def parse_comment(node, post_id, blog=None, parent_id=None, context=None):
    # И это тоже парсинг коммента. Не надо юзать эту функцию.

    context = dict(context) if context else {}
    classes = frozenset(node.get('class', '').split())

    # Вытаскиваем элемент с информацией
    info = node.xpath('.//*[@class="comment-info"][1]')
    comment_id = int(node.get('data-id') or info.get('data-id'))

    nick_node = None
    if info:
        info = info[0]
        nick_node = info.xpath('.//a[starts-with(@class, "comment-author")][1]')

    if not nick_node:
        # Если комментарий удалён или скрыт, его comment-info пустой
        if 'comment-deleted' not in classes and 'comment-hidden' not in classes:
            utils.logger.warning(
                'Comment %s in post %s has no comment-info! Please report to andreymal.',
                comment_id,
                post_id,
            )
        return None

    # Определяем, коммент из поста или из ленты (в ленте не все данные есть)
    vote_area = info.xpath('.//*[starts-with(@id, "vote_area_comment")][1]')
    is_full_comment = bool(vote_area and vote_area[0].xpath('.//div[contains(@class, "vote-up")]'))

    # Вытаскиваем всякую мелочёвку
    unread = "comment-new" in classes

    # Администратор может видеть удалённые и скрытые комментарии,
    # поэтому эти классы вполне могут здесь присутствовать
    deleted = "comment-deleted" in classes
    hidden = "comment-hidden" in classes

    nick = nick_node[0].text

    tm = info.xpath('.//time[1]')[0].get('datetime')
    utctime = utils.parse_datetime(tm)
    tm = time.strptime(tm[:-6], "%Y-%m-%dT%H:%M:%S")  # legacy

    # Вытаскиваем текст сообщения (с учётом utils.escape_comment_contents)
    body = node.xpath('div[@class="comment-content"][1]/div[1]')[0]
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

    # Если коммент из списка комментов, мы можем вытащить заголовок поста
    post_li = info.xpath('.//a[@class="blog-name"][1]')
    if post_li:
        post_li = post_li[0].getparent()
        post_title = post_li.xpath('a[@class="comment-path-topic"]')[0].text
        post_link = post_li.xpath('a[@class="comment-path-comments"]')[0].get('href')
        blog, post_id = parse_post_url(post_link)  # Перезаписываем входные параметры — наше более достоверно
        del post_link
    else:
        post_title = None
    del post_li

    # Достаём информацию о родительском комментарии
    if parent_id is None:
        parent_link = info.xpath('.//a[@class="goto goto-comment-parent"][1]')
        if parent_link:
            parent_link = parent_link[0]
            parent_href = parent_link.get('href', '')
            if '/comments/' in parent_href:
                # Парсим /comments/parent_id
                parent_id = int(parent_href.strip('/').rsplit('/', 1)[-1])
            elif '#comment' in parent_href:
                # Парсим #commentparent_id
                parent_id = int(parent_href.rsplit('#comment', 1)[-1])
            else:
                utils.logger.warning('Comment %s has invalid parent link! Please report to andreymal.', comment_id)
                parent_id = None

    # Проверяем возможность редактирования
    edit_btn = info.xpath('.//*[contains(@class, "comment-edit-bw")][1]')
    if edit_btn:
        edit_btn = edit_btn[0]
        edit_classes = edit_btn.get('class', '').split()

        if 'edit-timeout' in edit_classes:
            # TODO: если у поста есть класс is-moder или is-admin,
            # то редактировать на самом деле всё равно можно
            context['can_edit'] = False
        else:
            context['can_edit'] = True

        if not context['can_edit'] and not is_full_comment:
            # Для коммента из ленты отсутствие кнопки ничего не значит
            context['can_edit'] = None
    else:
        context['can_edit'] = None

    # TODO: проверить возможность удаления

    vote_total = None  # На новом Табуне для анонимов голоса скрыты
    context['can_vote'] = None
    context['vote_value'] = None

    # Достаём информаию о рейтинге
    if vote_area:
        vote_node = vote_area[0].xpath('.//span[@class="vote-count"]/text()[1]')
        vote_total = int(vote_node[0].replace("+", ""))
        if is_full_comment:  # проверка, что пост не из ленты (в ней классы полупустые)
            votecls = vote_area[0].get('class', '').split()
            context['can_vote'] = 'vote-enabled' in votecls
            if 'voted-up' in votecls:
                context['vote_value'] = 1
            elif 'voted-down' in votecls:
                context['vote_value'] = -1
    elif is_full_comment:
        context['can_vote'] = False

    # Достаём информацию об избранном
    favourited = False
    favourite_node = info.xpath('.//*[@class="comment-favourite"][1]')
    if favourite_node:
        favourited = favourite_node[0].find('div')
        context['favourited'] = favourited is not None and 'active' in favourited.get('class', '')
        favourite_str = favourite_node[0].find('span').text
        try:
            favourite = int(favourite_str) if favourite_str else 0
        except ValueError:
            favourite = None
    else:
        favourite = None
        context['favourited'] = False

    if body is not None:
        return Comment(tm, blog, post_id, comment_id, nick, body if raw_body is None else None, vote_total, parent_id,
                       post_title, unread, deleted, favourite, None, utctime, raw_body, hidden=hidden, context=context)


def parse_deleted_comment(node, post_id, blog=None, parent_id=None, context=None):
    # И это тоже парсинг коммента! Но не простого, а удалённого.
    try:
        comment_id = int(node.get('data-id'))
    except ValueError:
        return None

    context = dict(context) if context else {}

    classes = frozenset(node.get('class', '').split())
    unread = "comment-new" in classes
    deleted = "comment-deleted" in classes
    hidden = "comment-hidden" in classes
    if not deleted and not hidden:
        utils.logger.warning('Deleted comment %s is not deleted! Please report to andreymal.', comment_id)

    body = None
    nick = None
    tm = None
    post_title = None
    vote = None

    if parent_id is None:
        parent_wrapper = node.getparent().getparent()
        if (
            parent_wrapper is not None
            and parent_wrapper.tag == "div"
            and parent_wrapper.get("id", "").startswith("comment_wrapper_id_")
        ):
            parent_id = int(parent_wrapper.get("id").rsplit("_", 1)[-1])

    return Comment(tm, blog, post_id, comment_id, nick, body, vote, parent_id, post_title, unread, deleted, hidden=hidden, context=context)


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
