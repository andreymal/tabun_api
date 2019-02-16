tabun_api
---------

[![Build Status](https://travis-ci.org/andreymal/tabun_api.svg?branch=master)](https://travis-ci.org/andreymal/tabun_api)

API для сайта tabun.everypony.ru

Умеет:

* Логиниться по логину-паролю или TABUNSESSIONID+key
* Читать посты (в том числе из RSS), комментарии, личку, профили, информацию
  о блогах
* Создавать посты, комментарии, блоги и личные сообщения
* Удалять посты и блоги
* Редактировать посты, комментарии и информацию о блогах
* Ставить плюсики и минусики и смотреть ранее поставленные
* Работать с избранными постами, комментами и личными сообщениями
* Голосовать в опросах
* Рассылать инвайты в блоги
* Следить за активностью и прямым эфиром
* Писать заметки на пользователей
* Сидеть через прокси
* Обходить некоторые защиты CloudFlare
* А также выполнять всякую служебную мелочёвку: искать картинки, которые не
  смайлики, переводить html в txt и прочее

Требует Python 2.7/3.4, [lxml](http://lxml.de/) и
[iso8601](https://bitbucket.org/micktwomey/pyiso8601) для работы.
Также работает в PyPy версии 5.2 и выше.
Для использования SOCKS-прокси также следует установить
[PySocks](https://github.com/Anorov/PySocks). Некоторые опциональные функции
для работы с картинками требуют [Pillow](https://pillow.readthedocs.org/).


#### Установка через pip

```
pip install git+https://github.com/andreymal/tabun_api.git#egg=tabun_api[full]
```

Или если дополнительные плюшки не нужны:

```
pip install git+https://github.com/andreymal/tabun_api.git#egg=tabun_api
```

Или можно просто закинуть каталог `tabun_api` куда требуется и установить
зависимости вручную.


#### Простой пример с выводом заголовков последних постов

```
import tabun_api as api
for post in api.User().get_posts():
    print(post.title)
```

Документация с примерами: https://andreymal.org/tabun/api_doc/
