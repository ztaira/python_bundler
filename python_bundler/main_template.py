#!/usr/bin/env python3
import glob
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List

from packaging import version
from packaging.specifiers import SpecifierSet

HASH = "${deterministic_hash}"


def check_version() -> bool:
    system_version = version.parse(
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    constraint = "${python_version}"

    if constraint.startswith("^"):
        constraint_version = version.parse(constraint[1:])
        specifier1 = SpecifierSet(
            f">={constraint_version.major}.{constraint_version.minor}.{constraint_version.micro}"
        )
        specifier2 = SpecifierSet(f"<{constraint_version.major+1}.0.0")
        specifier = specifier1 & specifier2
    else:
        specifier = SpecifierSet(constraint)

    if system_version not in specifier:
        raise RuntimeError(
            f"Python version {sys.version_info} did not fit constraint set {specifier}"
        )

    return True


def unzip() -> str:
    files_dir = Path(f"{tempfile.gettempdir()}") / f"{HASH}.files"
    if not files_dir.exists():
        files_dir.mkdir(parents=True)
        with zipfile.ZipFile(Path(__file__).parent) as zfile:
            zfile.extractall(path=files_dir)

    return str(files_dir)


def install_pipfiles(files_dir: str):
    venv_dir = Path(f"/tmp/{HASH}")
    if not venv_dir.exists():
        # TODO: We could also include the python executable in the zipfile, and then
        # use it from the unpacked directory to ensure we're using exactly the same
        # version of python we expect. However, that's a Later Task.
        print(f"Creating virtualenv {venv_dir}")
        run_subprocess(args=[f"{sys.executable}", "-m", "venv", str(venv_dir)])
        run_subprocess(
            args=[
                f'{venv_dir / "bin" / "pip3"}',
                "install",
                *glob.glob(str(Path(files_dir) / "packages" / "*")),
                "--no-deps",
            ]
        )

    return venv_dir


def run_subprocess(args: List[str]):
    result = subprocess.run(args=args, capture_output=True, check=False)
    if result.returncode != 0:
        print(f"Command {' '.join(args)} failed with stdout: {result.stdout.decode()}")
        print(f"Command {' '.join(args)} failed with stderr: {result.stderr.decode()}")
        result.check_returncode()

    return result


def main():
    check_version()
    files_dir = unzip()
    venv_dir = install_pipfiles(files_dir)

    # This could be a bit confusing. Just to be clear here:
    # This executable file should be named the same as one of the entry points
    # in the tool.poetry.scripts section of the pyproject.toml it was built from.
    # That entry point should be active in venv_dir.

    # As a result, this executable should transparently pass its arguments through
    # to said entry point in venv_dir.
    result = subprocess.run(
        args=[venv_dir / "bin" / "${name}", *sys.argv[1:]], check=True
    )

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
