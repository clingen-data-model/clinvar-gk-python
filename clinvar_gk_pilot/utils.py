import time


def make_progress_logger(logger, fmt: str, max_value: int = 0, interval: int = 10):
    def log_progress(current_value, force=False):
        if getattr(log_progress, "prev_log_time", None) is None:
            log_progress.prev_log_time = time.time()
            log_progress.prev_value = 0
            log_progress.max_value = max_value
            return
        now = time.time()
        if force or now - log_progress.prev_log_time > interval:
            elapsed = now - log_progress.prev_log_time
            elapsed_value = current_value - log_progress.prev_value
            logger.info(
                fmt.format(
                    current_value=current_value,
                    elapsed=elapsed,
                    elapsed_value=elapsed_value,
                    max_value=log_progress.max_value,
                )
            )

            log_progress.prev_log_time = now
            log_progress.prev_value = current_value

    return log_progress
