#!/usr/bin/env python3
import sys
import subprocess
import json
from pathlib import Path
import logging


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def setup_uv_environment():
    logger.info("Setting up uv Python environment...")
    try:
        result = subprocess.run(
            ["uv", "sync"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("uv environment synced successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to sync uv environment: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("uv not found. Install uv: https://github.com/astral-sh/uv")
        return False


def create_flash_directories():
    logger.info("Creating required directories...")
    directories = [
        Path("./flash_sessions"),
        Path("./configs"),
        Path("./firmware"),
    ]
    for directory in directories:
        directory.mkdir(exist_ok=True)
        logger.info(f"  Created: {directory}")
    return True


def create_default_config():
    logger.info("Creating default configuration...")
    config_path = Path("./configs/flash_config.json")
    if config_path.exists():
        logger.info("  Configuration already exists")
        return True

    config = {
        "usb_vendor_id": 0x04E8,
        "usb_product_id": 0x685D,
        "usb_endpoint_out": 1,
        "usb_endpoint_in": 129,
        "block_size_kb": 2,
        "usb_timeout_ms": 5000,
        "max_retry_attempts": 3,
        "transport_mode": "auto_detect",
        "flash_mode": "sequential",
        "partition_order": "bootloader_first",
        "enable_verification": True,
        "enable_checksum_validation": True,
        "firmware_directory": "./firmware",
        "log_level": "INFO",
    }

    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"  Default config created: {config_path}")
        logger.info("  Edit firmware_directory path to your firmware location")
        return True
    except Exception as e:
        logger.error(f"Failed to create config: {e}")
        return False


def verify_dependencies():
    logger.info("Verifying Python dependencies...")
    required_modules = [
        "usb",
        "lz4",
        "pydantic",
        "structlog",
    ]

    missing = []
    for module in required_modules:
        try:
            __import__(module)
            logger.info(f"  ✓ {module}")
        except ImportError:
            logger.warning(f"  ✗ {module} (will be installed via uv sync)")
            missing.append(module)

    if missing:
        logger.info(f"Missing packages will be installed via uv sync: {', '.join(missing)}")
    return True


def create_readme_quickstart():
    logger.info("Creating quickstart guide...")
    quickstart_path = Path("./QUICKSTART.txt")
    quickstart_content = """Samsung SM-A376U Firmware Flash - Quick Start
=============================================

1. Prepare your firmware:
   - Extract firmware files to ./firmware/ directory
   - Files should be: AP.lz4, BL.lz4, CP.lz4, CSC.lz4
   - All files must be LZ4-compressed

2. Connect device in Download Mode:
   - Power off device
   - Press Volume Down + Home + Power simultaneously
   - When screen shows "Download Mode", connect via USB

3. Edit configuration:
   - Edit ./configs/flash_config.json
   - Verify firmware_directory points to extracted firmware
   - Adjust USB settings if needed (usually defaults work)

4. Verify firmware before flashing:
   uv run python cli_runner.py dry-run --config ./configs/flash_config.json

5. Flash the device:
   uv run python cli_runner.py flash --config ./configs/flash_config.json

6. Monitor progress:
   - Real-time progress in console output
   - Detailed logs in ./flash_sessions/flash_*.log
   - Transfer rate and ETA displayed per partition

7. Post-flash:
   - Device will disconnect after flash completion
   - Power cycle when prompted
   - Check logs for any verification errors

Troubleshooting:
- USB device not found: Check connection, run lsusb to verify
- LZ4 errors: Verify firmware files are actually LZ4-compressed
- Permission denied: Run with sudo or fix USB device permissions
- Timeout errors: Increase usb_timeout_ms in config, check USB cable quality

For detailed help:
  uv run python cli_runner.py --help
"""
    try:
        with open(quickstart_path, "w") as f:
            f.write(quickstart_content)
        logger.info(f"  Quickstart created: {quickstart_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create quickstart: {e}")
        return False


def check_system_requirements():
    logger.info("Checking system requirements...")

    try:
        result = subprocess.run(
            ["python3", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info(f"  ✓ Python: {result.stdout.strip()}")

        import sys
        version = sys.version_info
        if version.major < 3 or version.minor < 10:
            logger.error(f"  ✗ Python 3.10+ required (found {version.major}.{version.minor})")
            return False
    except Exception as e:
        logger.error(f"Failed to check Python: {e}")
        return False

    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info(f"  ✓ uv: {result.stdout.strip()}")
    except FileNotFoundError:
        logger.error("  ✗ uv not found. Install from: https://github.com/astral-sh/uv")
        return False
    except Exception as e:
        logger.error(f"Failed to check uv: {e}")
        return False

    return True


def main():
    logger.info("=== Samsung Firmware Flash Environment Initialization ===\n")

    steps = [
        ("System Requirements", check_system_requirements),
        ("uv Environment", setup_uv_environment),
        ("Dependencies", verify_dependencies),
        ("Directories", create_flash_directories),
        ("Default Configuration", create_default_config),
        ("Quickstart Guide", create_readme_quickstart),
    ]

    results = {}
    for step_name, step_func in steps:
        try:
            logger.info(f"\n[{step_name}]")
            result = step_func()
            results[step_name] = result
            if not result:
                logger.warning(f"  ⚠ {step_name} incomplete (may need manual setup)")
        except Exception as e:
            logger.error(f"  ✗ {step_name} failed: {e}")
            results[step_name] = False

    logger.info("\n=== Initialization Summary ===")
    all_success = all(results.values())

    for step_name, result in results.items():
        status = "✓" if result else "⚠"
        logger.info(f"{status} {step_name}")

    if all_success:
        logger.info("\n✓ Environment initialized successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Edit ./configs/flash_config.json with your firmware path")
        logger.info("2. Extract firmware files to ./firmware/ directory")
        logger.info("3. Run: uv run python cli_runner.py dry-run --config ./configs/flash_config.json")
        logger.info("4. Run: uv run python cli_runner.py flash --config ./configs/flash_config.json")
        logger.info("\nFor more help: uv run python cli_runner.py --help")
        return 0
    else:
        logger.warning("\n⚠ Some initialization steps incomplete. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
