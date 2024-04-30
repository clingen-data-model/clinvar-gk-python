import multiprocessing
import time


def _worker(task_start_times, task_queue, outputs_queue):
    """
    Worker process target that continuously listens for tasks.
    Defined at root of module so it can be pickled.
    """
    while True:
        task = task_queue.get()
        if task is None:  # None is a signal to shut down
            break
        task_id, func, args, kwargs = task
        try:
            # Store the start time as a timestamp to avoid serialization issues
            task_start_times[task_id] = time.time()
            val = func(*args, **kwargs)
            outputs_queue.put((task_id, val))
        finally:
            del task_start_times[task_id]


class MPTaskQueue:
    def __init__(self, num_workers, output_queue):
        self.num_workers = num_workers
        self.output_queue = output_queue
        self.tasks = multiprocessing.Queue(100)
        self.processes = []
        self.task_start_times = multiprocessing.Manager().dict()

    def add_task(self, func, *args, **kwargs):
        """
        Add a task to the queue with a unique task ID.
        """
        task_id = f"task-{time.time()}"  # Unique ID based on timestamp
        self.tasks.put((task_id, func, args, kwargs))
        return task_id

    def start(self):
        """
        Start the worker processes.
        """
        for _ in range(self.num_workers):
            p = multiprocessing.Process(
                target=_worker,
                args=(self.task_start_times, self.tasks, self.output_queue),
            )
            p.start()
            self.processes.append(p)

    def stop(self):
        """Stop all worker processes."""
        for _ in range(self.num_workers):
            self.tasks.put(None)
        for p in self.processes:
            p.join()

    def monitor_tasks(self):
        """Monitor and report the running time of each task."""
        for task_id, start_time in list(self.task_start_times.items()):
            elapsed_time = time.time() - start_time
            print(f"Task {task_id} has been running for {elapsed_time:.2f} seconds.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False  # Allows exceptions to propagate


# Example of how to use this TaskQueue as a process pool
def example_task(duration, message):
    print(f"Starting task: {message}")
    time.sleep(duration)
    print(f"Finished task: {message}")


if __name__ == "__main__":
    pass
    # with MPTaskQueue(num_workers=4) as pool:
    #     task_ids = [
    #         pool.add_task(example_task, 2, "Process data"),
    #         pool.add_task(example_task, 3, "Load data"),
    #         pool.add_task(example_task, 1, "Send notification"),
    #     ]
    #     time.sleep(1)  # Delay to allow tasks to start
    #     pool.monitor_tasks()  # Monitoring task durations
