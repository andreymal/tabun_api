#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name='tabun_api',
    version='0.6.3',
    description='Tabun Client Library',
    author='andreymal',
    license='MIT',
    url='https://github.com/andreymal/tabun_api',
    packages=['tabun_api'],
    install_requires=['lxml>=3.3'],
    extras_require={
        'imageutils': ['Pillow'],
    },
)
