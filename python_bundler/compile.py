from __future__ import annotations

import argparse
import importlib
import os
import re
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from string import Template
from typing import Dict, List, Set, cast

from poetry.core.masonry.builders.wheel import WheelBuilder
from poetry.core.packages.package import Package
from poetry.factory import Factory

import python_bundler

MAIN_TEMPLATE = Template(
    importlib.resources.read_text(python_bundler, "main_template.py")
)

PIP_DOWNLOAD_REGEX = r"Saved .*/(?P<package_name>.*)"
PIP_HASH_REGEX = r"--hash=(?P<package_hash>.*)"


def run_subprocess(args: List[str]) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(args=args, capture_output=True, check=False)
    if result.returncode != 0:
        print(
            f"Command {' '.join(args)} failed with stdout: {str(result.stdout)}",
        )
        print(
            f"Command {' '.join(args)} failed with stderr: {str(result.stderr)}",
        )
        result.check_returncode()

    return result


def get_package_name_from_pip_download_output(pip_output: str) -> str:
    for line in pip_output.split("\n"):
        temp = re.match(PIP_DOWNLOAD_REGEX, line)
        if temp:
            return temp.group("package_name")
    raise ValueError(f"Could not parse package name out of pip output: {pip_output}")


def get_packages_in_group(
    root_package: Package, package_index: Dict[str, Package], group_name: str
) -> Set[Package]:
    """Grabs the all the package dependencies in a given group"""
    # We can use a set here, since each package from the package_index should
    # be unique.
    packages: Set[Package] = set()
    for _, dependency in enumerate(
        root_package.with_dependency_groups(group_name, only=True).all_requires
    ):
        if package_index[dependency.name] == root_package:
            continue
        get_package_recursive_dependencies(
            package=package_index[dependency.name],
            package_index=package_index,
            viewed_packages=packages,
            root_package=root_package,
        )
    return packages


def get_package_recursive_dependencies(
    package: Package,
    package_index: Dict[str, Package],
    viewed_packages: Set[Package],
    root_package: Package,
) -> None:
    """Grabs all recursive dependencies of a package"""
    if package == root_package:
        return
    viewed_packages.add(package)
    for _, dependency in enumerate(package.all_requires):
        if package_index[dependency.name] not in viewed_packages:
            get_package_recursive_dependencies(
                package_index=package_index,
                package=package_index[dependency.name],
                viewed_packages=viewed_packages,
                root_package=root_package,
            )


def check_hash(
    dependency_name: str, dependency_package_dir: Path, package: Package
) -> bool:
    pip_hash = run_subprocess(
        args=["pip", "hash", f"{dependency_package_dir / dependency_name}"]
    )
    for line in pip_hash.stdout.decode().split("\n"):
        temp = re.match(PIP_HASH_REGEX, line)
        if temp:
            package_hash = temp.group("package_hash")
            if {
                "file": dependency_name,
                "hash": package_hash,
            } in package.files:
                return True
    return False


def bundle(entry_point_name: str, dirty_build: bool, keep_zipfiles: bool) -> int:
    poetry_inst = Factory().create_poetry()

    locked_repository = poetry_inst.locker.locked_repository()
    distribution_dir = Path(poetry_inst.file.path).parent / "dist"
    dependency_package_dir = distribution_dir / "packages"

    if not dependency_package_dir.exists():
        dependency_package_dir.mkdir(parents=True)
    # if we're doing a dirty build, no need to clean the dependency directory
    # otherwise, in the default case, unlink and re-download the dependencies
    if not dirty_build:
        print(f"Cleaning {dependency_package_dir}")
        for item in dependency_package_dir.iterdir():
            print(f"  Removing {item}")
            item.unlink()
        dependency_package_dir.rmdir()
        dependency_package_dir.mkdir(parents=True)

        # create a package index
        package_index: dict[str, Package] = {
            package.name: package for package in locked_repository.packages
        }
        package_index[poetry_inst.package.name] = poetry_inst.package
        # get a listing of the recursive packages in the default and dev groups
        default_packages = get_packages_in_group(
            root_package=poetry_inst.package,
            package_index=package_index,
            group_name="main",
        )
        dev_packages = get_packages_in_group(
            root_package=poetry_inst.package,
            package_index=package_index,
            group_name="dev",
        )
        all_packages = default_packages.union(dev_packages)
        if not set(locked_repository.packages) == all_packages:
            raise RuntimeError(
                f"Some packages were not listed in the dev or default groups: {set(locked_repository.packages).difference(all_packages)}"
            )

        # Only download the packages in the default group.
        # No need to include dev dependencies in the final compiled zipfile.
        packages_to_install = sorted([*default_packages], key=lambda pak: pak.name)
        for index, package in enumerate(packages_to_install):
            if package == poetry_inst.package:
                print(f"({index+1}/{len(packages_to_install)}) Skipping self {package}")
                continue
            print(
                f"({index+1}/{len(packages_to_install)}) Downloading {package}",
            )
            pip_download_output = subprocess.run(
                args=[
                    "pip",
                    "download",
                    # TODO: should this be name, pretty_name, complete_name, or something else?
                    f"{package.name}=={package.version}",
                    "--no-deps",
                ],
                cwd=dependency_package_dir,
                capture_output=True,
                check=True,
            )
            dependency_name = get_package_name_from_pip_download_output(
                pip_download_output.stdout.decode()
            )
            if not check_hash(
                dependency_name=dependency_name,
                dependency_package_dir=dependency_package_dir,
                package=package,
            ):
                raise RuntimeError(
                    f"Could not verify hash of dependency {dependency_name}"
                )
            print(
                f"        Verified hash of dependency {dependency_name}",
            )

    # build the project wheel
    wheel_filename = WheelBuilder.make_in(poetry_inst)

    # For every entry point:
    # - Create an zipfile called {entry_point_name}.zip
    # - Fill said zipfile with all the dependency files
    # - Add the project's built wheel to said zipfile
    # - Add a __main__.py extractor file to the zipfile
    # - Create an executable zipfile by concatenating a shebang file and the newly
    #   completed zipfile
    try:
        script_data = cast(Dict[str, str], poetry_inst.pyproject.data["tool"]["poetry"]["scripts"])  # type: ignore[index]
    except KeyError as _err:
        print("\n<error>No 'tool.poetry.scripts' found in the pyproject.toml</error>")
        return 1
    if entry_point_name:
        entry_points = {
            key: value for key, value in script_data.items() if key == entry_point_name
        }
        if not entry_points:
            raise ValueError(
                f"No valid entry points found. Options: {list(script_data.keys())}"
            )
    else:
        entry_points = dict(script_data.items())
    for name, _ in entry_points.items():
        zipfile_path = Path(poetry_inst.file.path).parent / "dist" / f"{name}.zip"
        if zipfile_path.exists():
            zipfile_path.unlink()
        with zipfile.ZipFile(zipfile_path, "w") as zipfile_executable:
            # add the dependency packages to the zipfile
            for root, _, files in os.walk(dependency_package_dir):
                for file in files:
                    filename = Path(root) / file
                    arcname = Path("packages") / file
                    print(f"Adding package {arcname}")
                    zipfile_executable.write(filename=filename, arcname=arcname)

            # add the main package to the zipfile
            filename = distribution_dir / wheel_filename
            arcname = Path("packages") / wheel_filename
            print(f"Adding package {arcname}")
            zipfile_executable.write(filename=filename, arcname=arcname)

            # add the __main__ file to the zipfile
            with tempfile.NamedTemporaryFile("w+") as main_entry_point:
                python_version = cast(str, poetry_inst.pyproject.data["project"]["requires-python"])  # type: ignore[index]
                main_entry_point.write(
                    MAIN_TEMPLATE.substitute(
                        python_version=python_version,
                        name=name,
                        deterministic_hash=f"{name}-{uuid.uuid4()}",
                    )
                )
                main_entry_point.seek(0)
                zipfile_executable.write(
                    filename=main_entry_point.name, arcname="__main__.py"
                )

        # create the actual executable from the zipfile
        with tempfile.NamedTemporaryFile("w") as shebangfile:
            shebangfile.write("#!/usr/bin/env python3\n")
            shebangfile.seek(0)
            # 2022-04-17: The first time I used 'cat' to actually
            # concatenate files.
            binary_info = run_subprocess(
                args=["/usr/bin/cat", shebangfile.name, f"{zipfile_path}"],
            ).stdout

        executable_name = distribution_dir / name
        with executable_name.open("wb") as writefile:
            writefile.write(binary_info)
        executable_name.chmod(0o764)

        if not keep_zipfiles:
            zipfile_path.unlink()

    return 0


def parse_args():
    main_parser = argparse.ArgumentParser()
    main_parser.add_argument(
        "--dirty-build", help="Directory to process", action="store_true"
    )
    main_parser.add_argument(
        "--keep-zipfiles", help="Directory to process", action="store_true"
    )
    main_parser.add_argument("entry_point_name", help="Directory to process")
    return main_parser.parse_args()


def entrypoint():
    arguments = parse_args()
    bundle(**dict(vars(arguments).items()))
