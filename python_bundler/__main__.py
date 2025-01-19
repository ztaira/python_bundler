import sys

from python_bundler.compile import entrypoint


def main():
    return entrypoint()


if __name__ == "__main__":
    sys.exit(main())
