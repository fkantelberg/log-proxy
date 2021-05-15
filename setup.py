import os

from setuptools import find_packages, setup


def read(fname):
    with open(os.path.join(os.path.dirname(__file__), fname)) as f:
        return f.read()


setup(
    name="logging-proxy",
    version="0.1",
    author="Florian Kantelberg",
    author_email="florian.kantelberg@mailbox.org",
    description="Proxy the log from one system to another",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="logging socket",
    url="https://github.com/fkantelberg/logging-proxy",
    packages=find_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    entry_points={"console_scripts": ["logging_proxy = logging_proxy.__main__:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
