import asyncio
import logging
import os

from watchdog.events import FileModifiedEvent, PatternMatchingEventHandler
from watchdog.observers import Observer
from watchdog.utils.patterns import match_any_paths


class WatcherHandler(PatternMatchingEventHandler):
    """Watcher class to observe changes in all specified files in the folder"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observed = {}

    def match_file(self, path):
        """Check if the path matches the patterns and folder"""
        return match_any_paths(
            [path],
            included_patterns=self.patterns,
            excluded_patterns=self.ignore_patterns,
            case_sensitive=self.case_sensitive,
        )

    def get_size(self, path):
        return self.observed.get(path, 0)

    def set_size(self, path, size):
        self.observed[path] = size

    def read_initial_size(self, path):
        """Read the initial size of the file to not send the entire file on start"""
        if os.path.isfile(path):
            if self.match_file(path):
                self.observed[path] = os.path.getsize(path)
            return

        for dirname, _, files in os.walk(path):
            for file in files:
                path = os.path.join(dirname, file)
                if self.match_file(path):
                    self.observed[path] = os.path.getsize(path)

    def on_new_line(self, path, line):
        """Send the line to the logging"""
        logging.getLogger(path).info(line)

    def on_modified(self, event):
        """React on modified files and append the new lines"""
        if not isinstance(event, FileModifiedEvent):
            return

        size = os.path.getsize(event.src_path)

        # Get the already observed lines
        current = self.get_size(event.src_path)
        if current >= size:
            self.set_size(event.src_path, size)
            return

        # Open the file and seek to the last position
        with open(event.src_path) as fp:
            fp.seek(current)

            # Read line by line and only use full lines
            for line in fp:
                stripped = line.strip()
                if line.endswith("\n") and stripped:
                    current += len(line)
                    self.on_new_line(event.src_path, stripped)

        # Update the position
        self.set_size(event.src_path, current)


async def watch(path, **kwargs):
    """Watch on files of in a directory and log new lines"""
    handler = WatcherHandler(**kwargs)
    handler.read_initial_size(path)
    observer = Observer()
    observer.schedule(handler, path=path, recursive=True)
    observer.start()

    try:
        while observer.is_alive():
            await asyncio.sleep(0.1)
    finally:
        observer.stop()
        observer.join()
