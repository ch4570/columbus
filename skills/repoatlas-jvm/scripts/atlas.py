"""Compatibility entrypoint for the installed RepoAtlas skill."""
import sys

sys.dont_write_bytecode = True

from repoatlas.cli import doctor, main

if __name__ == '__main__':
    raise SystemExit(main())
