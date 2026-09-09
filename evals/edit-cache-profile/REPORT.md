# One-file edit diagnosis

measure.py profiles an edit to Django encoding.py in an isolated source copy, then restores it. The recorded 17.37-second refresh includes profiler overhead. Namespace-prefix scanning generated 15.62 million generator iterations; parse-cache encoding took about 1.99 seconds cumulatively, including about 1.01 seconds of compression across the refresh. This led to the module-prefix optimization documented in ../python-module-prefix/REPORT.md rather than assuming compression was the primary cost.

The original source is untouched. Restoration checks file/symbol/edge counts only; the subsequent full comparison in python-module-prefix supplies the stronger facts/search/edge parity evidence. This diagnostic is not a model experiment or a baseline latency benchmark.
