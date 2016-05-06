Установка
=========

Через pip::

    pip install git+https://github.com/andreymal/tabun_api.git#egg=tabun_api[imageutils]

``imageutils`` подтянет `Pillow <https://pillow.readthedocs.org/>`_ для работы функции
:func:`~tabun_api.utils.find_good_image`, выбирающей картинки по их разрешению.

Если это не нужно, то Pillow можно не ставить::

    pip install git+https://github.com/andreymal/tabun_api.git#egg=tabun_api

А ещё можно просто закинуть каталог ``tabun_api`` куда требуется, не забыв установить
lxml и iso8601.

Для использования SOCKS-прокси также следует установить `PySocks <https://github.com/Anorov/PySocks>`_.

Для вывода предупреждений используется ``logging``. Если вам печатают
«No handlers could be found for logger "tabun_api"», то значит ваша версия Python
требует явной инициализации логгера, которой вы не сделали. Проще всего это
сделать так:

.. code-block:: python

    import logging
    logging.basicConfig()
