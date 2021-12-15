import asyncio
import os
import time
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

import pytest
from watchdog.events import FileModifiedEvent
from watchdog.observers import Observer

from log_proxy.watcher import WatcherHandler, watch


@pytest.fixture
def named_file():
    with NamedTemporaryFile("w+", suffix=".log") as fp:
        yield fp


def test_watcher_initial(named_file):
    path, name = os.path.split(named_file.name)
    handler = WatcherHandler(patterns=[name])
    # Read the file directly
    handler.read_initial_size(named_file.name)
    assert handler.observed == {named_file.name: 0}

    handler.observed = {}
    assert handler.observed == {}

    # Read everything in the folder
    named_file.write("hello\n")
    named_file.flush()
    handler.read_initial_size(path)
    assert handler.observed == {named_file.name: 6}


def test_watcher(named_file):
    try:
        path, name = os.path.split(named_file.name)
        handler = WatcherHandler(patterns=[name])
        handler.read_initial_size(named_file.name)

        observer = Observer()
        observer.schedule(handler, path=path, recursive=True)
        observer.start()

        named_file.write("hello\n")
        named_file.flush()
        time.sleep(0.1)

        mock = handler.on_new_line = MagicMock()

        named_file.write("test\n")
        named_file.flush()
        time.sleep(0.1)

        mock.assert_called_once_with(named_file.name, "test")
        mock.reset_mock()

        # Skip if the file is smaller now
        handler.observed[named_file.name] = 100
        named_file.seek(0)
        named_file.write("abc\n")
        named_file.flush()
        time.sleep(0.1)
        mock.assert_not_called()
    finally:
        observer.stop()
        observer.join()


def test_watcher_modified(named_file):
    event = FileModifiedEvent(named_file.name)

    handler = WatcherHandler()
    handler.read_initial_size(named_file.name)

    get_mock = handler.get_size = MagicMock(return_value=0)
    set_mock = handler.set_size = MagicMock()
    line_mock = handler.on_new_line = MagicMock(9)

    handler.on_modified(None)
    get_mock.assert_not_called()

    handler.on_modified(event)
    get_mock.assert_called_once_with(named_file.name)
    line_mock.assert_not_called()
    set_mock.assert_called_once_with(named_file.name, 0)
    set_mock.reset_mock()

    named_file.write("test\n")
    named_file.flush()

    handler.on_modified(event)
    line_mock.assert_called_once_with(named_file.name, "test")
    set_mock.assert_called_once_with(named_file.name, 5)


@pytest.mark.asyncio
@patch("log_proxy.watcher.Observer")
async def test_watch(mock, named_file):
    observer = mock.return_value
    observer.is_alive.side_effect = [True, False]

    path, name = os.path.split(named_file.name)
    await watch(path, patterns=[name])
    await asyncio.sleep(0.1)

    mock.assert_called_once()
    assert observer.is_alive.call_count == 2
    observer.schedule.assert_called_once()
    observer.start.assert_called_once()
    observer.stop.assert_called_once()
    observer.join.assert_called_once()
