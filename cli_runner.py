#!/usr/bin/env python3
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime
from advanced_flash_orchestrator import (
    AdvancedFlashOrchestrator,
    OrchestrationConfig,
    USBTransportMode,
    FlashMode,
    PartitionPriority,
)


class FlashCLI:
    def __init__(self):
        self.logger = logging.getLogger("FlashCLI")
        self.config: Optional[OrchestrationConfig] = None
        self.orchestrator: Optional[AdvancedFlashOrchestrator] = None
        self.session_log_dir = Path("./flash_sessions")
        self.session_log_dir.mkdir(exist_ok=True)

    def setup_logging(self, log_level: str = "INFO", session_id: Optional[str] = None):
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        log_file = self.session_log_dir / f"flash_{session_id}.log"

        handlers = [
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ]

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        for handler in handlers:
            handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level))

        for handler in handlers:
            root_logger.addHandler(handler)

        self.logger.info(f"Logging session started: {session_id}")
        self.logger.info(f"Log file: {log_file}")

        return log_file

    def load_config_from_file(self, config_path: Path) -> OrchestrationConfig:
        try:
            self.logger.info(f"Loading configuration from {config_path}")
            with open(config_path, "r") as f:
                config_dict = json.load(f)
            config = OrchestrationConfig(**config_dict)
            self.logger.info("Configuration loaded successfully")
            return config
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise

    def create_default_config(self, firmware_dir: Path) -> OrchestrationConfig:
        self.logger.info("Creating default configuration")
        config = OrchestrationConfig(firmware_directory=firmware_dir)
        return config

    def save_config(self, config: OrchestrationConfig, output_path: Path):
        try:
            config_dict = config.model_dump()
            config_dict["firmware_directory"] = str(config_dict["firmware_directory"])
            with open(output_path, "w") as f:
                json.dump(config_dict, f, indent=2)
            self.logger.info(f"Configuration saved to {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            raise

    def print_config_summary(self, config: OrchestrationConfig):
        self.logger.info("=== Configuration Summary ===")
        self.logger.info(f"USB Vendor ID: 0x{config.usb_vendor_id:04X}")
        self.logger.info(f"USB Product ID: 0x{config.usb_product_id:04X}")
        self.logger.info(f"Block Size: {config.block_size_kb} KB")
        self.logger.info(f"USB Timeout: {config.usb_timeout_ms} ms")
        self.logger.info(f"Max Retries: {config.max_retry_attempts}")
        self.logger.info(f"Transport Mode: {config.transport_mode.value}")
        self.logger.info(f"Flash Mode: {config.flash_mode.value}")
        self.logger.info(f"Partition Order: {config.partition_order.value}")
        self.logger.info(f"Checksum Validation: {config.enable_checksum_validation}")
        self.logger.info(f"Verification: {config.enable_verification}")
        self.logger.info(f"Firmware Directory: {config.firmware_directory}")

    async def execute_flash_sequence(self) -> bool:
        try:
            self.logger.info("=== Starting Flash Sequence ===")
            self.print_config_summary(self.config)

            self.orchestrator = AdvancedFlashOrchestrator(self.config)
            result = await self.orchestrator.execute_full_pipeline()

            self.logger.info("=== Flash Sequence Complete ===")
            return result
        except Exception as e:
            self.logger.error(f"Flash sequence failed: {e}")
            return False

    async def dry_run(self) -> bool:
        try:
            self.logger.info("=== Starting Dry Run ===")
            self.print_config_summary(self.config)

            self.orchestrator = AdvancedFlashOrchestrator(self.config)
            await self.orchestrator.initialize()

            self.logger.info("Loaded partitions:")
            for partition_name, partition_data in self.orchestrator.partitions.items():
                self.logger.info(
                    f"  {partition_name}: {partition_data.size_mb:.2f} MB "
                    f"(SHA256: {partition_data.checksum_sha256[:16]}...)"
                )

            self.logger.info("=== Dry Run Complete (No Hardware Write) ===")
            return True
        except Exception as e:
            self.logger.error(f"Dry run failed: {e}")
            return False

    async def verify_firmware_integrity(self) -> bool:
        try:
            self.logger.info("=== Starting Firmware Integrity Verification ===")

            from advanced_flash_orchestrator import PartitionLoader

            loader = PartitionLoader(self.config)
            partitions = await loader.load_all_partitions()

            self.logger.info("Firmware integrity check:")
            for partition_name, partition_data in partitions.items():
                self.logger.info(
                    f"  {partition_name}:")
                    f"    Size: {partition_data.size_mb:.2f} MB"
                    f"    SHA256: {partition_data.checksum_sha256}"
                )

            self.logger.info("=== Verification Complete ===")
            return True
        except Exception as e:
            self.logger.error(f"Verification failed: {e}")
            return False

    def create_config_template(self, output_path: Path):
        try:
            self.logger.info(f"Creating configuration template at {output_path}")

            template_config = {
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
                "firmware_directory": "/path/to/firmware",
                "log_level": "INFO",
            }

            with open(output_path, "w") as f:
                json.dump(template_config, f, indent=2)

            self.logger.info(f"Configuration template created: {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to create template: {e}")
            raise


def print_help():
    help_text = """
Samsung Firmware Flash Orchestration CLI
========================================

Usage: python cli_runner.py [COMMAND] [OPTIONS]

Commands:
  flash              Execute firmware flash (requires config file)
  dry-run            Verify firmware without writing to device
  verify             Check firmware integrity
  config-template    Generate configuration template
  config-update      Update configuration with custom values

Options:
  --config FILE      Path to configuration JSON file
  --firmware DIR     Firmware directory path
  --transport MODE   USB transport mode (heimdall, direct_pyusb, auto_detect)
  --flash-mode MODE  Flash mode (sequential, staged, write_only)
  --order PRIORITY   Partition order (bootloader_first, critical_first, system_first)
  --log-level LEVEL  Logging level (DEBUG, INFO, WARNING, ERROR)
  --output FILE      Output configuration file path
  --help            Show this help message

Examples:
  # Generate configuration template
  python cli_runner.py config-template --output config.json

  # Edit config.json with your firmware path, then flash
  python cli_runner.py flash --config config.json

  # Dry run to verify firmware without writing
  python cli_runner.py dry-run --config config.json

  # Verify firmware integrity
  python cli_runner.py verify --config config.json --firmware /path/to/firmware

  # Quick config update and flash
  python cli_runner.py flash --firmware /path/to/firmware --log-level DEBUG
"""
    print(help_text)


async def main():
    cli = FlashCLI()
    cli.setup_logging()

    if len(sys.argv) < 2:
        print_help()
        return 1

    command = sys.argv[1]

    config_path = None
    firmware_dir = None
    log_level = "INFO"
    output_path = None
    transport_mode = "auto_detect"
    flash_mode = "sequential"
    partition_order = "bootloader_first"

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--config" and i + 1 < len(sys.argv):
            config_path = Path(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--firmware" and i + 1 < len(sys.argv):
            firmware_dir = Path(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--log-level" and i + 1 < len(sys.argv):
            log_level = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_path = Path(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--transport" and i + 1 < len(sys.argv):
            transport_mode = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--flash-mode" and i + 1 < len(sys.argv):
            flash_mode = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--order" and i + 1 < len(sys.argv):
            partition_order = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--help":
            print_help()
            return 0
        else:
            i += 1

    cli.setup_logging(log_level)

    try:
        if command == "config-template":
            output = output_path or Path("./flash_config_template.json")
            cli.create_config_template(output)
            return 0

        if command == "flash":
            if config_path:
                cli.config = cli.load_config_from_file(config_path)
            elif firmware_dir:
                cli.config = cli.create_default_config(firmware_dir)
            else:
                cli.logger.error("Either --config or --firmware must be specified")
                return 1

            if firmware_dir:
                cli.config.firmware_directory = firmware_dir
            if transport_mode:
                cli.config.transport_mode = USBTransportMode(transport_mode)
            if flash_mode:
                cli.config.flash_mode = FlashMode(flash_mode)
            if partition_order:
                cli.config.partition_order = PartitionPriority(partition_order)

            cli.config.log_level = log_level

            result = await cli.execute_flash_sequence()
            return 0 if result else 1

        elif command == "dry-run":
            if config_path:
                cli.config = cli.load_config_from_file(config_path)
            elif firmware_dir:
                cli.config = cli.create_default_config(firmware_dir)
            else:
                cli.logger.error("Either --config or --firmware must be specified")
                return 1

            if firmware_dir:
                cli.config.firmware_directory = firmware_dir
            cli.config.log_level = log_level

            result = await cli.dry_run()
            return 0 if result else 1

        elif command == "verify":
            if config_path:
                cli.config = cli.load_config_from_file(config_path)
            elif firmware_dir:
                cli.config = cli.create_default_config(firmware_dir)
            else:
                cli.logger.error("Either --config or --firmware must be specified")
                return 1

            if firmware_dir:
                cli.config.firmware_directory = firmware_dir
            cli.config.log_level = log_level

            result = await cli.verify_firmware_integrity()
            return 0 if result else 1

        elif command == "config-update":
            if not config_path:
                cli.logger.error("--config must be specified for config-update")
                return 1

            cli.config = cli.load_config_from_file(config_path)

            if firmware_dir:
                cli.config.firmware_directory = firmware_dir
            if transport_mode:
                cli.config.transport_mode = USBTransportMode(transport_mode)
            if flash_mode:
                cli.config.flash_mode = FlashMode(flash_mode)
            if partition_order:
                cli.config.partition_order = PartitionPriority(partition_order)

            cli.config.log_level = log_level

            output = output_path or config_path
            cli.save_config(cli.config, output)
            return 0

        else:
            cli.logger.error(f"Unknown command: {command}")
            print_help()
            return 1

    except Exception as e:
        cli.logger.error(f"CLI execution failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
