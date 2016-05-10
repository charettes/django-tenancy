#!/usr/bin/env python
from __future__ import unicode_literals

from setuptools import setup, find_packages

from tenancy import __version__


setup(
    name='django-tenancy',
    version=__version__,
    description='Handle multi-tenancy in Django with no additional global state using schemas.',
    url='https://github.com/charettes/django-tenancy',
    author='Simon Charette',
    author_email='charette.s+pypi@gmail.com',
    install_requires=[
        'Django>=1.8',
    ],
    packages=find_packages(exclude=['tests', 'tests.*']),
    license='MIT License',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 1.8',
        'Framework :: Django :: 1.9',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    extras_require={
        'hosts': ['django-hosts'],
        'mutant': ['django-mutant>=0.2.1'],
    }
)
