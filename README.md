# Samsung SM-A376U Firmware Flash Orchestration Pipeline

Production-grade asynchronous firmware flashing pipeline for Samsung SM-A376U devices in Download Mode.

## Architecture Overview

### Core Components

**firmware_orchestration.py**
- Basic LZ4 decompression and USB-level firmware writing
- Heimdall protocol support
- Sequential partition flashing (AP, BL, CP, CSC)
- Comprehensive error handling and retry logic
- Progress tracking with transfer rate metrics

**advanced_flash_orchestrator.py**
- Multi-transport abstraction (Heimdall, Direct pyUSB, Auto-detect)
- Configurable partition ordering strategies
- Transfer metrics and detailed reporting
- Pydantic-based configuration validation
- Staged and flexible flash modes

**cli_runner.py**
- Command-line interface with multiple execution modes
- Configuration management (load, create, update, template generation)
- Dry-run verification without hardware writes
- Firmware integrity verification
- Session-based logging with file persistence

### Dependency Management

Uses `uv` for Python package management:

```bash
uv sync
uv run python firmware_orchestration.py
uv run python advanced_flash_orchestrator.py
uv run python cli_runner.py flash --config config.json
```

## Quick Start

### 1. Generate Configuration Template

```bash
uv run python cli_runner.py config-template --output flash_config.json
```

Edit `flash_config.json` with your firmware directory path:
```json
{
  "firmware_directory": "/path/to/extracted/firmware",
  "transport_mode": "auto_detect",
  "log_level": "INFO"
}
```

### 2. Verify Firmware Before Flash

```bash
uv run python cli_runner.py dry-run --config flash_config.json
```

### 3. Execute Flash Pipeline

```bash
uv run python cli_runner.py flash --config flash_config.json
```

## File Structure

### Firmware Layout

Device must have decompressed firmware files in directory:
- `AP.lz4` - Application partition
- `BL.lz4` - Bootloader
- `CP.lz4` - Modem/CP
- `CSC.lz4` - Consumer customization

All files are LZ4-compressed and will be decompressed during pipeline execution.

## Configuration

### OrchestrationConfig Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| usb_vendor_id | int | 0x04E8 | 0-65535 | Samsung USB vendor ID |
| usb_product_id | int | 0x685D | 0-65535 | Device product ID in Download Mode |
| usb_endpoint_out | int | 0x01 | 1-255 | USB OUT endpoint address |
| usb_endpoint_in | int | 0x81 | 1-255 | USB IN endpoint address |
| block_size_kb | int | 2 | {1,2,4,8,16} | Block size for transfers |
| usb_timeout_ms | int | 5000 | 1000-30000 | USB operation timeout |
| max_retry_attempts | int | 3 | 1-10 | Retry count on USB errors |
| transport_mode | str | auto_detect | heimdall, direct_pyusb, auto_detect | USB communication protocol |
| flash_mode | str | sequential | sequential, staged, write_only | Flash execution strategy |
| partition_order | str | bootloader_first | bootloader_first, critical_first, system_first | Partition write sequence |
| enable_verification | bool | true | - | Post-flash device verification |
| enable_checksum_validation | bool | true | - | SHA256 checksum validation |
| firmware_directory | str | /path/to/firmware | - | Firmware files location |
| log_level | str | INFO | DEBUG, INFO, WARNING, ERROR | Logging verbosity |

## CLI Commands

### flash
Execute complete firmware flashing pipeline.

```bash
uv run python cli_runner.py flash --config flash_config.json
uv run python cli_runner.py flash --firmware /path/to/firmware --log-level DEBUG
```

### dry-run
Verify firmware without writing to device. Useful for pre-flash validation.

```bash
uv run python cli_runner.py dry-run --config flash_config.json
```

### verify
Check firmware integrity and partition checksums.

```bash
uv run python cli_runner.py verify --config flash_config.json
```

### config-template
Generate default configuration template.

```bash
uv run python cli_runner.py config-template --output my_config.json
```

### config-update
Update existing configuration with new values.

```bash
uv run python cli_runner.py config-update --config flash_config.json \
  --firmware /new/path --transport heimdall --output updated_config.json
```

## Error Handling

### USB Communication Errors
Automatic retry with exponential backoff:
- 1st retry: 200ms delay
- 2nd retry: 400ms delay
- 3rd retry: 800ms delay
- Fails after max_retry_attempts

### LZ4 Decompression Failures
Caught at partition load time with detailed error messages including:
- File path that failed
- Decompression error details
- Recovery suggestions

### Flash Verification Errors
Checksum validation at partition completion:
- SHA256 hash computed on decompression
- Transmitted to device for verification
- Error counters tracked per partition

### Device State Verification
Post-flash validation ensures:
- Device responds after flash completion
- All partitions written correctly
- No corruption detected

## Transfer Metrics

Pipeline generates comprehensive metrics:

```json
{
  "status": "complete",
  "total_time_seconds": 120.5,
  "total_bytes_written": 2147483648,
  "total_bytes_expected": 2147483648,
  "overall_rate_mbps": 17.8,
  "partitions": {
    "AP": {
      "bytes_sent": 1073741824,
      "bytes_expected": 1073741824,
      "progress_percent": 100.0,
      "transfer_rate_mbps": 18.2,
      "elapsed_seconds": 58.9,
      "retry_count": 0,
      "verification_errors": 0,
      "is_complete": true
    }
  }
}
```

## Logging

Session logs saved to `./flash_sessions/` with timestamps:
- `flash_20250923_143022.log`
- Dual output: console + file
- Configurable log levels: DEBUG, INFO, WARNING, ERROR

## Transport Modes

### Auto-Detect (Default)
Attempts Heimdall protocol first, falls back to Direct pyUSB if unavailable.

### Heimdall
Uses Heimdall protocol (0x04E8/0x685D) for Samsung device communication.
Compatible with official Heimdall flashing tool.

### Direct pyUSB
Raw USB communication via pyusb library.
Lower-level alternative if Heimdall protocol unavailable.

## Partition Ordering Strategies

### bootloader_first (Default)
Sequence: BL → CP → AP → CSC
Critical bootloader and modem first for safety.

### critical_first
Sequence: BL → CP → AP → CSC
Same as bootloader_first.

### system_first
Sequence: AP → CP → BL → CSC
System partition written before bootloader (advanced users only).

## Safety Features

- ✅ Pre-flash firmware integrity verification
- ✅ Checksums validated on device after partition write
- ✅ Automatic USB error recovery with exponential backoff
- ✅ Transaction logs saved per session
- ✅ Dry-run mode for pre-flash validation
- ✅ Device state verification post-flash
- ✅ Complete error handling with no silent failures

## Requirements

- Python ≥ 3.10
- Samsung SM-A376U in Download Mode
- USB cable with data support
- Linux/macOS kernel driver support

## Dependencies

Managed via `pyproject.toml`:
- `pyusb>=1.2.1` - USB device communication
- `lz4>=4.3.2` - LZ4 decompression
- `pydantic>=2.5.0` - Configuration validation
- `structlog>=24.1.0` - Advanced logging
- `asyncio-contextmanager>=1.0.0` - Async context support
- `attrs>=23.2.0` - Class decorators
