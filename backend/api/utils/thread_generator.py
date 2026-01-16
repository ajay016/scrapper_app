import threading
import queue






class ThreadedGenerator:
    def __init__(self, target_func, *args, **kwargs):
        self.queue = queue.Queue()
        self.sentinel = object()
        self.thread = threading.Thread(
            target=self._run, 
            args=(target_func, args, kwargs), 
            daemon=True
        )
        self.thread.start()

    def _run(self, func, args, kwargs):
        try:
            # We call the scraper function HERE, inside the new thread
            for item in func(*args, **kwargs):
                self.queue.put(item)
        except Exception as e:
            # If the scraper fails, we pass the error to the main thread
            self.queue.put(e)
        finally:
            self.queue.put(self.sentinel)

    def __iter__(self):
        while True:
            item = self.queue.get()
            if item is self.sentinel:
                return
            if isinstance(item, Exception):
                print(f"Scraper Error: {item}")
                return
            yield item