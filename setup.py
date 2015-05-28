#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name='tabun_api',
    version='0.6.1',
    description='Tabun Client Library',
    author='andreymal',
    license='MIT',
    url='https://github.com/andreymal/tabun_api',
    packages=find_packages(),
    install_requires=['lxml>=3.3']
)
