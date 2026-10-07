# RW1 local BOOTTIME semantics and capability

The locally installed glibc bits/time.h documents CLOCK_BOOTTIME as a system-wide monotonic clock that includes time spent in suspension. The header and Linux time.h raw bytes are archived with SHA256. Local time_namespaces(7) and proc_pid_stat(5) raw compressed files and decoded originals are archived for namespace/process identity provenance.

The Python CLOCK_BOOTTIME integer-nanosecond API was read twice with the exact values and platform recorded in report.json. These reads test present API capability only. They do not validate real suspend/resume, hypervisor/host pause, restart, or fork behavior, and do not authorize an actual run. No backend was initialized, no render or recovery occurred, and no network was used.
