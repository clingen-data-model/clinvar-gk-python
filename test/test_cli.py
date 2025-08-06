from clinvar_gk_pilot.cli import parse_args


def test_parse_args():
    argv = ["--filename", "test.txt"]
    opts = parse_args(argv)
    assert opts["filename"] == "test.txt"
    assert opts["parallelism"] == 1
    assert opts["liftover"] is False
    assert len(opts) == 3
