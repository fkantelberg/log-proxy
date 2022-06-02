import os

from setuptools import find_packages, setup


def read(fname):
    with open(os.path.join(os.path.dirname(__file__), fname)) as f:
        return f.read()


setup(
    name="log-proxy",
    version="1.4",
    author="Florian Kantelberg",
    author_email="florian.kantelberg@mailbox.org",
    description="Proxy the log from one system to another",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="logging socket proxy",
    url="https://github.com/fkantelberg/log-proxy",
    packages=find_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    entry_points={"console_scripts": ["log_proxy = log_proxy.__main__:main"]},
    extras_require={
        "observe": ["watchdog"],
        "postgres": ["psycopg2"],
        "mongodb": ["pymongo"],
        "mysql": ["pymysql"],
        "influxdb": ["influxdb"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
