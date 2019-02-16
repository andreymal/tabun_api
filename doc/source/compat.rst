Совместимость с Python 2 и Python 3
===================================

Для работы в обоих версиях питона ``tabun_api`` содержит модуль ``compat``, содержащий используемые здесь типы и модули, имеющие разные названия в разных версиях питона:

* ``PY2``: True при запуске в Python 2 или False для любой другой версии;
* ``text_types``: ``(basestring,)`` для Python 2 или ``(str,)``;
* ``text``: ``unicode`` для Python 2 или ``str``;
* ``binary``: ``str`` для Python 2 или ``bytes``;
* ``urequest``: ``urllib2`` для Python 2 или ``urllib.request``;
* ``HTTPException`` из ``httplib`` для Python 2 или ``http.client``;
* ``BaseCookie`` из ``Cookie`` для Python 2 или ``http.cookies``;
* ``html_unescape``: ``HTMLParser.HTMLParser().unescape`` для Python 2 или ``html.unescape`` для Python >= 3.4.
