Установка
=========

Через pip:

::

    pip install git+https://github.com/andreymal/tabun_api.git#egg=tabun_api[imageutils]

``imageutils`` подтянет `Pillow <https://pillow.readthedocs.org/>`_ для работы функции ``tabun_api.utils.find_good_image``, выбирающий картинки по их разрешению.

Если это не нужно, то Pillow можно не ставить:

::

    pip install git+https://github.com/andreymal/tabun_api.git#egg=tabun_api

А ещё можно просто закинуть каталог ``tabun_api`` куда требуется, не забыв установить lxml.
