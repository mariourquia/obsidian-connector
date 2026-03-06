# Scheduled Automation

The obsidian-connector can run morning briefings, evening closes, and weekly
reviews automatically using macOS launchd.

## How it works

1. A launchd agent fires at configured times (default: 8am, 6pm, Sunday 9am)
2. `run_scheduled.py` calls the Python API directly (no LLM, no API calls)
3. A structured summary is written to your daily note
4. A macOS notification tells you it ran

## Setup

Run the installer with scheduling enabled:

```bash
./scripts/install.sh --with-scheduling
```

Or manually:

1. Copy `config.yaml` to `~/.config/obsidian-connector/schedule.yaml`
2. Edit times and timezone
3. Install the launchd agents:

```bash
# Morning
cp scheduling/com.obsidian-connector.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

## Configuration

Edit `~/.config/obsidian-connector/schedule.yaml`:

```yaml
timezone: America/New_York
morning:
  enabled: true
  time: "08:00"
evening:
  enabled: true
  time: "18:00"
weekly:
  enabled: true
  day: sunday
  time: "09:00"
notification:
  enabled: true
  method: osascript
  open_on_click: obsidian
```

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
