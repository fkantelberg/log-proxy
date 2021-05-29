import asyncio
import logging
import os

from watchdog.events import FileModifiedEvent, PatternMatchingEventHandler
from watchdog.observers import Observer
from watchdog.utils.patterns import match_any_paths


class WatcherHandler(PatternMatchingEventHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observed = {}

    def match_file(self, path):
        return match_any_paths(
            [path],
            included_patterns=self.patterns,
            excluded_patterns=self.ignore_patterns,
            case_sensitive=self.case_sensitive,
        )

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
        current = min(self.observed.get(event.src_path, 0), size)
        if current >= size:
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
        self.observed[event.src_path] = current


async def watch(path, **kwargs):
    """Watch on files of in a directory and log new lines"""
    handler = WatcherHandler(**kwargs)
    handler.read_initial_size(path)
    observer = Observer()
    observer.schedule(handler, path=path, recursive=True)
    observer.start()

    try:
        while True:
            await asyncio.sleep(0.5)
    finally:
        observer.stop()
        observer.join()
