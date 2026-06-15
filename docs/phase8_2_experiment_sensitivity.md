# Phase 8.2 Experiment Sensitivity

Phase 8.2 removes the previous flat benchmark behavior by connecting metrics to runtime mechanisms.

## Network Mechanisms

- PCSC tick decisions are sent as cloud-to-edge network messages.
- Network outage recovery uses reconnect and heartbeat-delivery callbacks.
- Cloud unavailable scenarios schedule an actual timeout event.
- Packet loss can drop supervision decisions or recovery heartbeat messages, causing retry events.
- Jitter and reordering are sampled by `NetworkSimulator` with the configured seed.

## Mode Mechanisms

- PCSC invokes cloud supervision periodically.
- ETEAC avoids periodic ticks and only uploads failure/replan summaries when local execution needs cloud help.
- AUTO records risk and cache signals, prepares a transition, and commits only at a safe boundary.

## Validity Views

Batch output includes:

- `mode_by_scenario`
- `network_by_scenario`
- `mode_by_network`
- `seed_variability`
- `validity_guard`

The guard checks that modes, networks, and seeds are not all identical and that fault detection latency is not always zero.
