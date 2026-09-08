"""Source and installed-skill entrypoint for Columbus."""
import sys

sys.dont_write_bytecode = True

from columbus.cli import doctor, main

if __name__ == '__main__':
    raise SystemExit(main())
