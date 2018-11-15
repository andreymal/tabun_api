Модуль tabun_api
================

----------
Переменные
----------

.. autodata:: tabun_api.http_host

.. autodata:: tabun_api.halfclosed

.. autodata:: tabun_api.http_headers

.. autodata:: tabun_api.post_url_regex

.. autodata:: tabun_api.post_file_regex

-----------------------------
Самое главное тут: класс User
-----------------------------

.. autoclass:: tabun_api.User
   :members:

----------------------
Вспомогательные классы
----------------------

У всех этих классов названия и содержимое полей соответствуют
аргументам конструктора.

``time`` содержит объекты ``time.struct_time`` по времени сервера,
а ``utctime`` — объекты ``datetime.datetime`` по UTC (без
установленного ``tzinfo`` для совместимости с Python 2).

Для объектов, содержащих словарь ``context`` и загруженных не через
AJAX, присутствуют следующие значения:

* ``context['http_host']`` — хост, с которого был получен объект
* ``context['url']`` — ссылка, по которой был получен объект
* ``context['username']`` — имя пользователя, если он был
  авторизован при получении объекта

Всё из этого может отсутствовать, поэтому получать их лучше
методом ``get`` словаря: ``obj.context.get('username')``

.. autoclass:: tabun_api.Post
   :members:

.. autoclass:: tabun_api.Comment
   :members:

.. autoclass:: tabun_api.Download
   :members:

.. autoclass:: tabun_api.Blog
   :members:

.. autoclass:: tabun_api.StreamItem
   :members:

.. autoclass:: tabun_api.UserInfo
   :members:

.. autoclass:: tabun_api.Poll
   :members:

.. autoclass:: tabun_api.TalkItem
   :members:

.. autoclass:: tabun_api.ActivityItem
   :members:
