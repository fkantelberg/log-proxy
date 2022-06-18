[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/log-proxy)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# log-proxy

This package implements a logging server which can be secured with TLS. The server can forward the
logs to another server allowing the definition of gateways. The transmission happens using JSON
instead of pickle used by pythons SocketHandler to prevent code execution.

The main purpose of this project is to aggregate logs via the network inside of a database like
PostgreSQL or MongoDB. The client is able to collect the logs from different sources.

This tool is not designed to later process, view, or manage the logs inside of the database.

## Features

- Log aggregation and proxy servers
- Forward the logs in a server to another server or database (MongoDB, PostgreSQL)
- Logging handlers to send logs to the logging server from existing apps
- Client tool for testing
- Secure the transmission with TLS and token authentication

## Usage examples

#### Start a logging server and forward the logs to a MongoDB database

`$ python3 -m log_proxy server mongodb --db logs --db-table log <...>`

#### Start a logging server and forward the logs to the next server

`$ python3 -m log_proxy server socket --forward <host>`

#### Start client for testing

`$ python3 -m log_proxy client --forward <host> --log-stdin`
