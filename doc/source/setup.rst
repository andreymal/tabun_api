Установка
=========

Через pip::

    pip install git+https://github.com/andreymal/tabun_api.git#egg=tabun_api[full]

``full`` подтянет `Pillow <https://pillow.readthedocs.org/>`_ для работы функции
:func:`~tabun_api.utils.find_good_image`, выбирающей картинки по их разрешению,
`PySocks <https://github.com/Anorov/PySocks>`_ для возможности работы с прокси-
сервером и `Js2Py <https://github.com/PiotrDabkowski/Js2Py>`_ для обхода защиты
CloudFlare.

Если всё это не нужно, то можно их не ставить::

    pip install git+https://github.com/andreymal/tabun_api.git#egg=tabun_api

А ещё можно просто закинуть каталог ``tabun_api`` куда требуется, не забыв установить
lxml и iso8601.

Для вывода предупреждений используется ``logging``. Если вам печатают
«No handlers could be found for logger "tabun_api"», то значит ваша версия Python
требует явной инициализации логгера, которой вы не сделали. Проще всего это
сделать так:

.. code-block:: python

    import logging
    logging.basicConfig()
