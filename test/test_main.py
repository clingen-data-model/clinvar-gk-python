from clinvar_gk_pilot.main import parse_args


def test_parse_args():
    argv = ["--filename", "test.txt"]
    opts = parse_args(argv)
    assert opts["filename"] == "test.txt"
    assert len(opts) == 1
