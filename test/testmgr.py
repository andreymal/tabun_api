#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals, print_function

import os
import re
import sys
import time
import difflib

import testutil


def clean_dynamic_data(data, user):
    # Ключики новые при каждом перезапуске скрипта
    if user.session_id:
        data = data.replace(user.session_id.encode('utf-8'), b'00000000')
    if user.security_ls_key:
        data = data.replace(user.security_ls_key.encode('utf-8'), b'FFFFFFFF')

    # Прямой эфир на то и прямой, чтобы постоянно обновляться
    f = data.find(b'<div class="js-block-stream-content">')
    if f >= 0:
        f = data.find(b'<ul', f + 1, f + 200)
    if f >= 0:
        f = data.find(b'<', f + 1, f + 200)
    if f >= 0:
        f2 = data.find(b'</ul>', f + 1, f + 25000)
        if f2 >= 0:
            data = data[:f] + data[f2:]

    # Блоги иногда плюсуют
    f = data.find(b'<div class="js-block-blogs-content">')
    if f >= 0:
        f = data.find(b'<ul', f + 1, f + 200)
    if f >= 0:
        f = data.find(b'<', f + 1, f + 200)
    if f >= 0:
        f2 = data.find(b'</ul>', f + 1, f + 25000)
        if f2 >= 0:
            data = data[:f] + data[f2:]

    # Аватарки иногда меняют
    data = re.sub(
        r'<img +src="[^"]+?"([^>]+?)class="avatar"'.encode('utf-8'),
        b'<img src="//cdn.everypony.ru/static/local/avatar_male_48x48.png"\\1class="avatar"',
        data,
        flags=re.DOTALL,
    )

    data = re.sub(
        r'<img +src="[^"]+?"([^>]+?)class="comment-avatar"'.encode('utf-8'),
        b'<img src="//cdn.everypony.ru/static/local/avatar_male_24x24.png"\\1class="comment-avatar"',
        data,
        flags=re.DOTALL,
    )

    # Денежку иногда донатят
    # Прямой эфир на то и прямой, чтобы постоянно обновляться
    f = data.find(b'<section class="block block-type-donations">')
    if f >= 0:
        f = data.find(b'<ul class="donation-list', f + 1, f + 600)
    if f >= 0:
        f = data.find(b'<', f + 1, f + 600)
    if f >= 0:
        f2 = data.find(b'</ul>', f + 1, f + 25000)
        if f2 >= 0:
            data = data[:f] + data[f2:]

    # Разум Табуна каждый раз новый
    f = data.find('<header class="block-header sep"><h3>Разум Табуна</h3></header>'.encode('utf-8'))
    if f >= 0:
        f = data.find(b'<div class="quote', f + 1, f + 600)
    if f >= 0:
        f = data.find(b'<', f + 1, f + 600)
    if f >= 0:
        f2 = data.find(b'</div>', f + 1, f + 25000)
        if f2 >= 0:
            data = data[:f] + data[f2:]

    return data


def diffs(args):
    if not args or not args[0]:
        print_help()
        return

    cache_dir = os.path.abspath(args[0])
    if not os.path.isdir(args[0]):
        os.mkdir(cache_dir)

    # В чём будем искать изменения
    # (ссылки взяты от балды с предположением, что со стороны юзеров их никто не поменяет)
    urls = [
        ('/blog/service/6599.html', '403.html'),
        ('/blog/87325.html', '87325.html'),
        ('/profile/Jelwid/', 'Jelwid.html'),
        ('/page/rules/', 'rules.html'),
        ('/page/faq/', 'faq.html'),
        ('/page/faq/editor/', 'faq_editor.html'),
    ]

    downloaded = []

    import tabun_api as api
    from tabun_api.compat import PY2
    user = api.User()

    # Страницу 404 качаем отдельно, так как она через обработку исключения
    print('404.html', end=' ')
    sys.stdout.flush()

    try:
        user.urlopen('/404/')
    except api.TabunError as exc:
        if exc.code != 404:
            raise RuntimeError('/404/ not returned 404!')
        data = exc.exc.read()
        data = exc.data + data
        downloaded.append(('404.html', data))
    else:
        raise RuntimeError('/404/ not returned 404!')
    print()

    # Качаем всё остальное
    for url, name in urls:
        print(name, end=' ')
        sys.stdout.flush()
        data = user.urlread(url)
        downloaded.append((name, data))
        print()

    # Обрабатываем то, что скачали
    for name, data in downloaded:
        # Чистим страницы от аватарок и прямого эфира — мы и так знаем, что они всегда меняются
        cleaned_data = clean_dynamic_data(data, user)

        path = os.path.join(cache_dir, (name.encode('utf-8') if PY2 else name))

        # Если в каталоге файла ещё нет, то это первый запуск и просто сохраняем
        if not os.path.isfile(path):
            with open(path, 'wb') as fp:
                fp.write(cleaned_data)
            print(name, 'stored')
            continue

        # Загружаем предыдущие данные для сравнения
        with open(path, 'rb') as fp:
            old_cleaned_data = fp.read()
        if old_cleaned_data == cleaned_data:
            print(name, 'not changed')
            continue

        # Данные изменились — генерируем патч для чтения человеком
        print(name, 'changed!', end=' ')
        sys.stdout.flush()

        assert '.' in name
        tm = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime(os.stat(path).st_mtime))
        old_name = name[:name.rfind('.')] + '.' + tm + name[name.rfind('.'):]
        old_path = os.path.join(cache_dir, (old_name.encode('utf-8') if PY2 else old_name))
        os.rename(path, old_path)

        diff_name = old_name + '.patch'
        diff_path = os.path.join(cache_dir, (diff_name.encode('utf-8') if PY2 else diff_name))

        with open(path, 'wb') as fp:
            fp.write(cleaned_data)

        old_lines = [x + '\n' for x in old_cleaned_data.decode('utf-8', 'replace').split('\n')]
        new_lines = [x + '\n' for x in cleaned_data.decode('utf-8', 'replace').split('\n')]

        with open(diff_path, 'wb') as fp:
            for line in difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=old_name,
                tofile=name,
                n=3,
            ):
                fp.write(line.encode('utf-8'))
        print('Diff saved as', diff_name)


def tmpl(args):
    if '--guest' in args:
        guest = True
        args.remove('--guest')
    else:
        guest = False

    if '--raw' in args:
        raw = True
        args.remove('--raw')
    else:
        raw = False
    if not args or not args[0]:
        print_help()
        return

    if guest:
        testutil.guest_mode = True

    data = testutil.load_file(args[0]).decode('utf-8')

    if not raw:
        data = data.replace('src="//', 'src="https://')
        data = data.replace('href="//', 'href="https://')

    print(data)


def print_help():
    print('Usage: {} tmpl [--guest] [--raw] <filename.html>'.format(sys.argv[0]))
    print('Usage: {} diffs <storage_directory>'.format(sys.argv[0]))


def main():
    if len(sys.argv) < 2:
        print_help()
        return
    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == 'tmpl':
        tmpl(args)

    elif cmd == 'diffs':
        diffs(args)

    else:
        print_help()
        return


if __name__ == '__main__':
    main()
