#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from setuptools import setup, find_packages

def readme():
    with open('README.rst') as f:
        return f.read()

setup(
    name='cdp-client',
    version='2.0.0',
    packages=find_packages(),
    install_requires=[
        'promise==2.2.1',
        'websocket-client==0.56.0',
        'protobuf==3.7.1',
        'mock==3.0.5'],
    keywords=["cdp cdpstudio studio client cdp-client cdp_client"],
    url='https://github.com/CDPTechnologies/PythonCDPClient',
    license='MIT',
    author='CDP Technologies AS',
    author_email='info@cdptech.com',
    description='Provides an API that allows to interact with CDP applications',
	long_description=readme(),
    test_suite='nose.collector',
    tests_require=['nose'],
    include_package_data=True,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Topic :: Software Development',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6']
)
