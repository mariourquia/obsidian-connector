# Scheduled Automation

The obsidian-connector can run morning briefings, evening closes, and weekly
reviews automatically using macOS launchd.

## How it works

1. A launchd agent fires at a configured time (default: morning at 08:00)
2. `run_scheduled.py` calls the Python API directly (no LLM, no API calls)
3. If the workflow is enabled in config, a summary is written to your daily note
4. A macOS notification tells you it ran

## Setup

Run the installer and answer "y" when prompted for scheduled automation:

```bash
./scripts/install.sh
# ... when prompted: "Install scheduled daily briefing (macOS launchd)? [y/N]"
```

Or manually:

1. Copy `config.yaml` to `~/.config/obsidian-connector/schedule.yaml`
2. Edit the `enabled` flags for each workflow
3. Install the launchd agent:

```bash
cp scheduling/com.obsidian-connector.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

**Note:** The installer currently sets up a single launchd job for the morning
briefing at 08:00. To add evening or weekly automation, create additional
plist files with different `ProgramArguments` (`evening` or `weekly`) and
`StartCalendarInterval` values, then `launchctl load` each one.

## Configuration

Edit `~/.config/obsidian-connector/schedule.yaml`:

```yaml
morning:
  enabled: true
evening:
  enabled: true
weekly:
  enabled: true
notification:
  enabled: true
  method: osascript  # osascript (built-in) or terminal-notifier
```

The `enabled` flag controls whether `run_scheduled.py` executes or exits
silently for each workflow.

## Manual testing

```bash
python3 scheduling/run_scheduled.py morning
python3 scheduling/run_scheduled.py evening
python3 scheduling/run_scheduled.py weekly
```

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
rm ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```
