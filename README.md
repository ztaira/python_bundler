# Python Bundler (experimental)

This repo creates executable zipfiles similar to
[zipapp](https://docs.python.org/3/library/zipapp.html),
[pex](https://docs.pex-tool.org/index.html),
and 
[shiv](https://github.com/linkedin/shiv).

It's useful when one:
- Wants to create compiled packages from a lockfile
- Wants to be able to debug the resulting environment without unzipping
- Doesn't mind an initial startup cost to create the virtualenv
- Wants to use mostly python tooling instead of rejiggering everything to e.g.
  Bazel

It does not solve some of the core problems with python and its packaging, such
as:
- Some python packages will not work on different python versions,
  architectures, etc
- Python takes up a lot of space relative to its functionality
- Python is duck-typed at runtime

## Alternatives:
| Package Name                                                                  | Is publicly supported                                    | Requires different directory structure | Installs all dependencies automatically                                                                         | Easy to debug                              |
| ---                                                                           | ---                                                      | ---                                    | ---                                                                                                             | ---                                        |
| [zipapp](https://docs.python.org/3/library/zipapp.html)                       | yes, included with python                                | Maybe, must have `__main__.py`         | No, they must be manually included via `pip install -r requirements.txt --target <directory>` before build time | No, must unzip the file to edit            |
| [pex](https://docs.pex-tool.org/index.html)                                   | yes, large project                                       | No, works on console scripts           | Can specify requirements.txt manually at build time                                                             | No, must unzip the file to edit            |
| [shiv](https://github.com/linkedin/shiv)                                      | yes, past 1.0.0, by linkedin                             | No, works on console scripts           | No, must specify the dependencies on the command line at build time                                             | No, must unzip the file to edit            |
| this repo                                                                     | no                                                       | No, works on console scripts           | Yes, uses poetry lockfile                                                                                       | Yes, can edit the installation venv        |
| [bazel](https://rules-python.readthedocs.io/en/latest/pypi-dependencies.html) | yes, but many modern-python conveniences have a time lag | Yes                                    | One can wire it up with requirements.txt                                                                        | No, but it can made to be with some effort |

## Rough Comparisons:
| Package Name                                                                  | Runtime                               | Command                                                                     | English definition                                                                                                      | Size |
| ---                                                                           | ---                                   | ---                                                                         | ---                                                                                                                     | ---  |
| [zipapp](https://docs.python.org/3/library/zipapp.html)                       | 1.9-2.5s                              | `pip install . --target python_bundler && python -m zipapp python_bundler/` | Install the current package to the target directory, then make a zipapp out of said directory                           | 48M  |
| [pex](https://docs.pex-tool.org/index.html)                                   | 5s for the first run, then 3.2-3.5s   | `pex '.' --console-script python_bundler --output project_bundle.pex`       | Make a pex env containing the current package, then make an executable pexfile out of the python_bundler console script | 21M  |
| [shiv](https://github.com/linkedin/shiv)                                      | 2.5s for the first run, then 0.6-0.8s | `shiv -c python_bundler -o python_bundler.shiv '.'`                         | Make a shiv file using python_bundler console script. Install the current directory.                                    | 20M  |
| this repo                                                                     | 11s for the first run, then 0.6-0.7s  | `python_bundler python_bundler`                                             | Use the current directory's lockfile to create an executable zipfile from the python_bundler console script             | 16M  |
| [bazel](https://rules-python.readthedocs.io/en/latest/pypi-dependencies.html) | n/a                                   | n/a                                                                         | n/a                                                                                                                     | n/a  |
