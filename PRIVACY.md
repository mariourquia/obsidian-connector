# Privacy Policy

## obsidian-connector

### Local-only operation

obsidian-connector runs entirely on your local machine. No data leaves your device at any point during operation.

### No telemetry or analytics

This software does not include any telemetry, analytics, crash reporting, or usage tracking. There are no external network calls of any kind.

### Vault access

All communication with the Obsidian desktop app occurs via local IPC (inter-process communication). The connector invokes the Obsidian CLI binary on your machine to read and write vault data. No vault contents are transmitted over a network.

### Mutation logging

All mutating operations (appending to daily notes, logging decisions, creating notes) are logged locally to `~/.obsidian-connector/logs/` in JSONL format. These logs exist solely for your auditability and never leave the machine.

### No user data collection

obsidian-connector does not collect, store, or transmit any personal information, user identifiers, or behavioral data. There are no accounts, no sign-ups, and no authentication tokens sent to external services.
