Совместимость с Python 2 и Python 3
===================================

Для работы в обоих версиях питона ``tabun_api`` содержит модуль ``compat``, содержащий используемые здесь типы и модули, имеющие разные названия в разных версиях питона:

* ``PY2``: True при запуске в Python 2 или False для любой другой версии;
* ``urequest``: ``urllib2`` для Python 2 или ``urllib.request``;
* ``HTTPException`` из ``httplib`` для Python 2 или ``http.client``;
* ``BaseCookie`` из ``Cookie`` для Python 2 или ``http.cookies``;
* ``text_types``: ``(basestring,)`` для Python 2 или ``(str,)``;
* ``text``: ``unicode`` для Python 2 или ``str``;
* ``binary``: ``str`` для Python 2 или ``bytes``.

На момент написания документации подключение к Табуну через прокси-сервер доступно только для Python 2.
