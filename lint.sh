#!/usr/bin/env bash

set -xo pipefail

# exit mode is off in order to run all commands and report all errors
# but we still want to exit with error if any of the commands fail
had_error=0

src_dir=clinvar_gk_pilot
if [[ "$1" == "apply" ]]; then
    # Uses each linter's option to apply the changes if it is supported
    black $src_dir || had_error=1
    isort $src_dir || had_error=1
    ruff --fix $src_dir || had_error=1
    pylint --disable=C,R,W $src_dir || had_error=1
else
    # Check-only mode
    black --check $src_dir || had_error=1
    isort --check-only $src_dir || had_error=1
    ruff check $src_dir || had_error=1
    pylint --disable=C,R,W $src_dir || had_error=1
fi

exit $had_error
