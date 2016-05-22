#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup


setup(
    name='tabun_api',
    version='0.7.2',
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
        'imageutils': ['Pillow>=3.0'],
        'proxy': ['PySocks>=1.5'],
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
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
