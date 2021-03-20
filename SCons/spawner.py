#!/usr/bin/env python
import sys
import pickle
import subprocess


def main():
    while True:
        try:
            params = pickle.load(sys.stdin.buffer)
        except EOFError:
            break

        try:
            proc = subprocess.Popen(params["args"], env=params["env"], close_fds=True)
            ret = proc.wait()
        except Exception as e:
            ret = e

        pickle.dump(ret, sys.stdout.buffer)
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
