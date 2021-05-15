[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/log-proxy)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# log-proxy

This package implements a logging server which can be secured with TLS. The server can forward the
logs to another server allowing the definition of gateways. The transmission happens using JSON
instead of pickle used by pythons SocketHandler to prevent code execution.

## Features

- Create a logging server
- Forward of logs to another logging server
- Read logs from stdin
- Secure the transmission with TLS

## Usage examples

#### Start a logging server

Without SSL: `$ python3 -m log_proxy`

With SSL: `$ python3 -m log_proxy --cert <...> --key <...>`

#### Start a logging server and forward logs to another server

Without SSL: `$ python3 -m log_proxy -f <IP>`

With SSL: `$ python3 -m log_proxy -f <IP> --forward-ca <...>`

#### Forward the a file to a logging server

`$ tail -f <file> | python3 -m log_proxy --log-stdin --no-server -f <IP>`
