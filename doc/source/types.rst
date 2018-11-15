Типы данных
===========

Почти все данные, которые парсит tabun_api, помещаются в соответствующие
классы. Они определны в модуле ``tabun_api.types``, но можно импортировать
и напрямую из ``tabun_api``.

У всех этих классов названия и содержимое полей соответствуют
аргументам конструктора.

Для получения доступа ко времени поста или комментария используйте атрибут
``utctime`` — это объект ``datetime.datetime``, хранящий время в UTC (без
установленного ``tzinfo`` для совместимости с Python 2).
Атрибут ``time`` хранит ``time.struct_time`` по времени сервера и
не рекомендуется к использованию: он оставлен для обратной совместимости
и может быть удалён в будущем.

Данные, которые относятся только к текущему пользователю (его оценки, статус
добавления в избранное, статус подписки и т.п.) хранятся в словаре
``context``. В нём же хранится адрес сайта, с которого были скачаны данные.

Для объектов, содержащих словарь ``context``, чаще всего доступны
следующие значения:

* ``context['http_host']`` — хост, с которого был получен объект
* ``context['url']`` — ссылка, по которой был получен объект
* ``context['username']`` — имя пользователя, если он был
  авторизован при получении объекта

Всё из этого может отсутствовать, поэтому получать их лучше
методом ``get`` словаря: ``obj.context.get('username')``. Однако отсутствие
``http_host`` нежелательно: без него не работает свойство ``url``,
присутствующее в некоторых классах.

.. autoclass:: tabun_api.types.Post
   :members:

.. autoclass:: tabun_api.types.Comment
   :members:

.. autoclass:: tabun_api.types.Download
   :members:

.. autoclass:: tabun_api.types.Blog
   :members:

.. autoclass:: tabun_api.types.StreamItem
   :members:

.. autoclass:: tabun_api.types.UserInfo
   :members:

.. autoclass:: tabun_api.types.Poll
   :members:

.. autoclass:: tabun_api.types.TalkItem
   :members:

.. autoclass:: tabun_api.types.ActivityItem
   :members:
