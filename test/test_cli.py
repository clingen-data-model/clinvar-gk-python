from clinvar_gk_pilot.cli import parse_args


def test_parse_args():
    argv = ["--filename", "test.txt"]
    opts = parse_args(argv)
    assert opts["filename"] == "test.txt"
    assert opts["parallelism"] == 1
    assert opts["liftover"] is False
    assert opts["task_timeout"] == 60
    assert len(opts) == 4


def test_parse_args_task_timeout():
    opts = parse_args(["--filename", "test.txt", "--task-timeout", "120"])
    assert opts["task_timeout"] == 120
