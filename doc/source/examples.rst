Примеры
=======

Все примеры написаны под Python 3. Для Python 2 нужно поменять `input` на `raw_input` и перед примерами выполнить:

.. code-block:: python

    from __future__ import print_function, unicode_literals


Заголовки последних постов
--------------------------

.. code-block:: python

    import time
    import tabun_api as api

    user = api.User()  # anonymous
    posts = user.get_posts("/index/newall/")

    for post in posts:
        # посты отсортированы по дате публикации (новые в конце)
        print(time.strftime("%H:%M", post.time), post.author, post.title)


Ну, или с авторизацией
----------------------

.. code-block:: python

    import time
    import getpass
    import tabun_api as api

    username = input("Username: ")
    passwd = getpass.getpass("Password: ")

    user = api.User(login=username, passwd=passwd)
    posts = user.get_posts("/blog/night-ponyville/newall/")

    for post in posts:
        print(time.strftime("%H:%M", post.time), post.author, post.title)


Первонах (код не проверялся)
----------------------------

.. code-block:: python

    import time
    import getpass
    import tabun_api as api

    username = input("Username: ")
    passwd = getpass.getpass("Password: ")
    user = api.User(login=username, passwd=passwd)
    ok = False

    while True:
        posts = user.get_posts("/index/newall/")
        for post in posts:
            if post.blog == "comicsworkshop" and post.title.startswith("ИнтерБРЕДации: "):
                print(user.comment(post.post_id, "Первый"))
                ok = True
                break
        if ok:
            break
        time.sleep(5)


Прямой эфир
-----------

Работает на допущении, что дата написания комментария тем больше, чем больше его id (известен `один случай <https://tabun.everypony.ru/blog/comicsworkshop/46415.html#comment2498188>`_, когда это не так).

.. code-block:: python

    import time
    import tabun_api as api

    user = api.User()

    max_comment_id = 0
    while True:
        try:
            comments = user.get_comments("/comments/")
        except api.TabunError as e:
            print()
            print("Error:", e.message)
            time.sleep(10)
            continue

        for comment_id in sorted(comments.keys()):
            if comment_id > max_comment_id:
                c = comments[comment_id]
                max_comment_id = comment_id
                print()
                print('[{tm}] <{author}> {title}'.format(
                    tm=time.strftime("%H:%M:%S", c.time),
                    author=c.author,
                    title=c.post_title
                ))
                print(api.utils.htmlToString(c.body))
        time.sleep(5)


Активность
----------

Выводит не более 20 новых элементов за раз.

.. code-block:: python

    import time
    import tabun_api as api

    def print_act(item):
        # Секунд во времени Табун не предоставляет
        print(time.strftime("[%H:%M]", item.date), item.username, end=' ')
        if item.type == item.POST_ADD:
            print('добавил новый пост "{}" ({}/{})'.format(item.title, item.blog, item.post_id))

        elif item.type == item.COMMENT_ADD:
            print('прокомментировал пост "{}" ({}/{}) ({})'.format(item.title, item.blog, item.post_id, item.comment_id))
            print(' ', item.data)

        elif item.type == item.POST_VOTE:
            print('оценил пост "{}" ({}/{})'.format(item.title, item.blog, item.post_id))

        elif item.type == item.COMMENT_VOTE:
            print('оценил комментарий к посту "{}" ({}/{}) ({})'.format(item.title, item.blog, item.post_id, item.comment_id))

        elif item.type == item.USER_VOTE:
            print('оценил пользователя {}'.format(item.data))

        else:
            print(item.type)

    user = api.User()

    old_items = []
    while 1:
        acts = user.get_activity()[1]
        new_items = []

        for x in acts:
            # активность в порядке добавления, но новые — в начале
            if x in old_items:
                # при удалении постов активность может пропадать, поэтому
                # сравниваем не с последней активностью из предыдущего
                # запроса, а со всеми
                break
            new_items.append(x)
        old_items = acts

        for x in reversed(new_items):
            print_act(x)
        time.sleep(5)



Простейший бот в личке
----------------------

.. code-block:: python

    import time
    import tabun_api as api

    def parse_command(message):
        if message == "ping":
            return "pong"
        elif message == "time":
            return time.strftime("%Y-%m-%d :%H:%M:%S")

    user = api.User("guest", "123456")

    while True:
        for talk in user.get_talk_list():
            if not talk.unread:
                continue
            for comment in user.get_talk(talk.talk_id).comments.values():
                if not comment.unread:
                    continue
                message = api.utils.htmlToString(comment.body)
                print('<', message)
                answer = parse_command(message)
                if answer:
                    print('>', answer)
                    try:
                        user.comment(talk.talk_id, body=answer, reply=comment.comment_id, typ='talk')
                    except api.TabunError as exc:
                        print(exc.message)
        time.sleep(10)

