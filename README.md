# Bassdrive Stream Recorder

A robust Python script for recording MP3 streams from Bassdrive radio with automatic retry functionality and disconnection handling.

## Features

- **Scheduled Recording**: Start recording at a specific time or immediately
- **Configurable Duration**: Set recording length in minutes
- **Robust Connection Handling**: Automatic retry with exponential backoff
- **Resume Capability**: Appends to existing files on reconnection instead of overwriting
- **Progress Monitoring**: Real-time progress updates with file size and time remaining
- **Graceful Error Handling**: Saves partial recordings even on failure

## Installation

### Requirements

- Python 3.6 or higher
- `requests` library

### Setup

1. Clone or download the script
2. Install required dependencies:
   ```bash
   pip install requests
   ```

## Usage

### Basic Examples

Record immediately for 2 hours (default):
```bash
./showrec.py
```

Record for 1 hour starting now:
```bash
./showrec.py --duration 60
```

Schedule recording to start at 8:00 PM for 90 minutes:
```bash
./showrec.py --start-time 20:00 --duration 90
```

Record with custom filename:
```bash
./showrec.py --output my_show.mp3 --duration 120
```

### Advanced Configuration

Record with increased retry attempts and custom timeouts:
```bash
./showrec.py --max-retries 1000 --retry-delay 3 --connection-timeout 45
```

Record from a different stream URL:
```bash
./showrec.py --url http://example.com/stream --duration 60
```

## Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--start-time` | None | Start time in HH:MM format (24-hour). Records immediately if not specified |
| `--duration` | 120 | Recording duration in minutes |
| `--output` | Auto-generated | Output filename (auto: bassdrive_YYYYMMDD_HHMM.mp3) |
| `--url` | Bassdrive stream | Stream URL to record from |
| `--max-retries` | 500 | Maximum retry attempts on connection failure |
| `--retry-delay` | 5 | Initial delay between retries in seconds |
| `--connection-timeout` | 30 | Connection timeout in seconds |

## Retry and Recovery Behavior

### Connection Retry Logic
- **Exponential Backoff**: Starts with configured delay, doubles on each failure
- **Maximum Delay**: Capped at 60 seconds to avoid excessive waits
- **Jitter**: Adds randomness (0.5x to 1.5x) to prevent server overload
- **Persistent**: Default 500 retry attempts ensures high reliability

### File Handling
- **Resume Recording**: Detects existing files and appends new data
- **Progress Preservation**: Maintains total recording time across disconnections
- **Safe Writes**: Uses binary append mode for seamless file continuation

### Error Scenarios
- **Network Interruptions**: Automatically retries with backoff
- **Stream Drops**: Reconnects and resumes recording
- **Timeout Handling**: Configurable connection timeouts
- **Graceful Shutdown**: Ctrl+C preserves recorded content

## Output Files

Files are saved in MP3 format with automatic naming based on recording start time:
- Format: `bassdrive_YYYYMMDD_HHMM.mp3`
- Example: `bassdrive_20250924_1430.mp3`
- **Note**: Timestamp reflects when recording actually begins, not when script starts

## Monitoring and Logging

The script provides detailed console output including:
- Connection status with success/failure indicators
- Retry attempt progress with remaining attempts
- Recording progress every 30 seconds
- File size information (total and newly written)
- Time remaining and elapsed time tracking

## Troubleshooting

### Common Issues

**Connection Failures**
- Check internet connectivity
- Verify stream URL is accessible
- Increase `--connection-timeout` for slow networks

**Frequent Disconnections**
- Increase `--max-retries` for better persistence
- Adjust `--retry-delay` based on network stability
- Monitor network quality during recording

**File Permission Errors**
- Ensure write permissions in output directory
- Check available disk space
- Verify output path is valid

### Getting Help

Run with `--help` to see all available options:
```bash
./showrec.py --help
```

## Examples

### Typical Use Cases

**Record a 2-hour show starting at 9 PM:**
```bash
./showrec.py --start-time 21:00 --duration 120
```

**High-reliability recording with maximum retries:**
```bash
./showrec.py --max-retries 1000 --retry-delay 2
```

**Quick 30-minute test recording:**
```bash
./showrec.py --duration 30 --output test_recording.mp3
```

**Resume interrupted recording (just restart with same filename):**
```bash
./showrec.py --output existing_recording.mp3 --duration 60
```

## License

This project is provided as-is for personal use. Please respect the terms of service of the streaming services you record from.