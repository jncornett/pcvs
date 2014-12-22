#!/usr/bin/env python3

from setuptools import setup

setup(
    name="pCVS",
    version="0.1dev2",
    description="Python CVS wrapper",
    author="Joel Cornett",
    author_email="joel.cornett@gmail.com",
    url="https://github.com/jncornett/pcvs",
    dependency_links=[
        "https://github.com/jncornett/shellwrap/tarball/master#egg=shellwrap-0.1dev1"
        ],
    py_modules=["pcvs"]
    )
