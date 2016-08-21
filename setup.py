#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re

from setuptools import setup


with open('tabun_api/__init__.py', 'rb') as fp:
    for line in fp:
        line = line.decode('utf-8-sig')
        m = re.search(r"^__version__ = '([^']+)'$", line)
        if m:
            version = m.group(1)
            break

imageutils_require = ['Pillow>=3.0']
proxy_require = ['PySocks>=1.5']
cf_require = ['Js2Py>=0.39']


setup(
    name='tabun_api',
    version=version,
    description='Tabun Client Library',
    author='andreymal',
    author_email='andriyano-31@mail.ru',
    license='MIT',
    url='https://github.com/andreymal/tabun_api',
    platforms='any',
    packages=['tabun_api'],
    zip_safe=False,
    install_requires=['lxml>=3.3', 'iso8601>=0.1.10'],
    extras_require={
        'imageutils': imageutils_require,
        'proxy': proxy_require,
        'cf': cf_require,
        'full': imageutils_require + proxy_require + cf_require,
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
