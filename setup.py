#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from setuptools import setup, find_packages

def readme():
    with open('README.rst') as f:
        return f.read()

setup(
    name='cdp-client',
    version='2.2.2',
    packages=find_packages(),
    install_requires=[
        'promise',
        'websocket-client<=0.56.0',
        'protobuf<=3.20.0',
        'mock'],
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
    python_requires=">=3.8",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Topic :: Software Development',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11']
)
