# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name='tpparser',
    version='0.1.0',
    description='Parsing of SOP data',
    author='Anton Rau',
    author_email='anton.rau@uzh.ch',
    url='https://github.com/BodenmillerGroup/TPParser',
    packages=find_packages(include=['tpparser']),
    install_requires=[],
    entry_points={
        'console_scripts': [
            'tpparser=tpparser.__main__:main',
        ],
    },
)
