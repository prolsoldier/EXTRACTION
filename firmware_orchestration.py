import asyncio
import hashlib
import io
import logging
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import lz4.frame
import usb.core
import usb.util


logger = logging.getLogger(__name__)


class FirmwarePartType(Enum):
    AP = "AP"
    BL = "BL"
    CP = "CP"
    CSC = "CSC"


@dataclass
class FirmwarePart:
    part_type: FirmwarePartType
    data: bytes
    offset: int = 0
    file_path: Path = None
    checksum: str = field(default="")

    def __post_init__(self):
        if not self.checksum:
            self.checksum = hashlib.sha256(self.data).hexdigest()

    @staticmethod
    def from_lz4_file(file_path: Path, part_type: FirmwarePartType) -> "FirmwarePart":
        try:
            with open(file_path, "rb") as f:
                compressed_data = f.read()
            decompressed = lz4.frame.decompress(compressed_data)
            return FirmwarePart(
                part_type=part_type,
                data=decompressed,
                file_path=file_path,
            )
        except Exception as e:
            raise FirmwareDecompressionError(
                f"Failed to decompress {part_type.value} from {file_path}: {e}"
            )


@dataclass
class HeimdallUSBConfig:
    vendor_id: int = 0x04E8
    product_id: int = 0x685D
    ep_out: int = 0x01
    ep_in: int = 0x81
    block_size: int = 2048
    timeout_ms: int = 5000
    max_retries: int = 3


class FirmwareException(Exception):
    pass


class FirmwareDecompressionError(FirmwareException):
    pass


class USBCommunicationError(FirmwareException):
    pass


class FlashVerificationError(FirmwareException):
    pass


class HeimdallProtocol:
    CMD_FILE_TRANSFER = 0x02
    CMD_DATA_TRANSFER = 0x03
    CMD_STATUS = 0x06
    CMD_FILE_PART_SIZE = 0x08
    CMD_FLASH_START = 0x09

    RESP_SUCCESS = 0x00
    RESP_DEVICE_IDENTIFIER = 0x05
    RESP_FLASH_START = 0x0A
    RESP_FLASH_DATA_TRANSFER = 0x0B


class USBDevice:
    def __init__(self, config: HeimdallUSBConfig = None):
        self.config = config or HeimdallUSBConfig()
        self.device = None
        self.in_transfer = False
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> bool:
        async with self._connect_lock:
            try:
                self.device = usb.core.find(
                    idVendor=self.config.vendor_id,
                    idProduct=self.config.product_id,
                )
                if self.device is None:
                    raise USBCommunicationError(
                        f"Device not found: {self.config.vendor_id:04x}:{self.config.product_id:04x}"
                    )

                if self.device.is_kernel_driver_active(0):
                    try:
                        self.device.detach_kernel_driver(0)
                    except usb.core.USBError as e:
                        raise USBCommunicationError(f"Failed to detach kernel driver: {e}")

                self.device.set_configuration()
                logger.info(f"Connected to device: {self.device.manufacturer} {self.device.product}")
                return True
            except Exception as e:
                logger.error(f"USB connection failed: {e}")
                raise USBCommunicationError(f"USB connection failed: {e}")

    async def disconnect(self):
        try:
            if self.device:
                usb.util.release_interface(self.device, 0)
                self.device = None
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")

    async def send_data(self, data: bytes, retry: int = 0) -> bool:
        try:
            if not self.device:
                raise USBCommunicationError("Device not connected")

            self.device.write(self.config.ep_out, data, self.config.timeout_ms)
            return True
        except usb.core.USBTimeoutError as e:
            if retry < self.config.max_retries:
                await asyncio.sleep(0.1 * (2 ** retry))
                return await self.send_data(data, retry + 1)
            raise USBCommunicationError(f"USB timeout on send: {e}")
        except Exception as e:
            raise USBCommunicationError(f"USB send failed: {e}")

    async def receive_data(self, length: int, retry: int = 0) -> bytes:
        try:
            if not self.device:
                raise USBCommunicationError("Device not connected")

            data = self.device.read(self.config.ep_in, length, self.config.timeout_ms)
            return bytes(data)
        except usb.core.USBTimeoutError as e:
            if retry < self.config.max_retries:
                await asyncio.sleep(0.1 * (2 ** retry))
                return await self.receive_data(length, retry + 1)
            raise USBCommunicationError(f"USB timeout on receive: {e}")
        except Exception as e:
            raise USBCommunicationError(f"USB receive failed: {e}")

    async def send_command(self, command: int, params: bytes = b"") -> bytes:
        try:
            packet = struct.pack("<I", command) + params
            await self.send_data(packet)
            response = await self.receive_data(4)
            if len(response) < 4:
                raise USBCommunicationError(f"Invalid response length: {len(response)}")
            return response
        except Exception as e:
            raise USBCommunicationError(f"Command send failed: {e}")


@dataclass
class FlashProgress:
    total_size: int = 0
    transferred_size: int = 0
    current_part: str = ""
    parts_completed: int = 0
    total_parts: int = 0
    start_time: float = field(default_factory=time.time)

    def update(self, bytes_transferred: int, part_name: str = ""):
        self.transferred_size += bytes_transferred
        if part_name:
            self.current_part = part_name

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def transfer_rate_mbps(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed < 1:
            return 0.0
        return (self.transferred_size / (1024 * 1024)) / elapsed

    @property
    def estimated_remaining_seconds(self) -> float:
        if self.transfer_rate_mbps < 0.01:
            return 0.0
        remaining_mb = (self.total_size - self.transferred_size) / (1024 * 1024)
        return remaining_mb / self.transfer_rate_mbps

    @property
    def progress_percent(self) -> float:
        if self.total_size == 0:
            return 0.0
        return (self.transferred_size / self.total_size) * 100


class FirmwareFlasher:
    def __init__(self, usb_config: HeimdallUSBConfig = None):
        self.usb = USBDevice(usb_config or HeimdallUSBConfig())
        self.progress = FlashProgress()
        self.firmware_parts: Dict[FirmwarePartType, FirmwarePart] = {}

    async def load_firmware_images(self, firmware_dir: Path) -> bool:
        try:
            firmware_files = {
                FirmwarePartType.AP: firmware_dir / "AP.lz4",
                FirmwarePartType.BL: firmware_dir / "BL.lz4",
                FirmwarePartType.CP: firmware_dir / "CP.lz4",
                FirmwarePartType.CSC: firmware_dir / "CSC.lz4",
            }

            for part_type, file_path in firmware_files.items():
                if not file_path.exists():
                    raise FirmwareException(f"Firmware file not found: {file_path}")
                try:
                    logger.info(f"Loading {part_type.value} from {file_path}")
                    part = FirmwarePart.from_lz4_file(file_path, part_type)
                    self.firmware_parts[part_type] = part
                    logger.info(
                        f"Loaded {part_type.value}: {len(part.data)} bytes, "
                        f"checksum: {part.checksum[:16]}..."
                    )
                except FirmwareDecompressionError as e:
                    raise FirmwareException(f"Failed to load {part_type.value}: {e}")

            total_size = sum(len(part.data) for part in self.firmware_parts.values())
            self.progress.total_size = total_size
            self.progress.total_parts = len(self.firmware_parts)
            logger.info(f"Total firmware size: {total_size / (1024*1024):.2f} MB")
            return True
        except Exception as e:
            logger.error(f"Firmware loading failed: {e}")
            raise FirmwareException(f"Firmware loading failed: {e}")

    async def initialize_device(self) -> bool:
        try:
            logger.info("Initializing USB device...")
            await self.usb.connect()
            logger.info("USB device initialized")
            return True
        except USBCommunicationError as e:
            logger.error(f"Device initialization failed: {e}")
            raise FirmwareException(f"Device initialization failed: {e}")

    async def begin_flash_session(self) -> bool:
        try:
            logger.info("Beginning flash session")
            response = await self.usb.send_command(HeimdallProtocol.CMD_FLASH_START)
            if len(response) < 4:
                raise FlashVerificationError("Invalid flash start response")
            logger.info("Flash session started")
            return True
        except Exception as e:
            logger.error(f"Flash session initialization failed: {e}")
            raise FlashVerificationError(f"Flash session initialization failed: {e}")

    async def write_firmware_part(self, part: FirmwarePart) -> bool:
        try:
            data_stream = io.BytesIO(part.data)
            part_size = len(part.data)
            offset = 0
            part_name = part.part_type.value

            logger.info(
                f"Writing {part_name} partition ({part_size / (1024*1024):.2f} MB)"
            )

            await self._send_partition_start(part_name, part_size)

            while offset < part_size:
                chunk_size = min(self.usb.config.block_size, part_size - offset)
                chunk = data_stream.read(chunk_size)
                if not chunk:
                    break

                await self._write_block(chunk, offset, part_name)
                self.progress.update(chunk_size, part_name)
                offset += chunk_size

                log_percent = (offset / part_size) * 100
                logger.info(
                    f"{part_name} progress: {log_percent:.1f}% "
                    f"({offset / (1024*1024):.2f}/{part_size / (1024*1024):.2f} MB) "
                    f"Rate: {self.progress.transfer_rate_mbps:.2f} MB/s "
                    f"ETA: {self.progress.estimated_remaining_seconds:.0f}s"
                )

            await self._finalize_partition(part_name, part.checksum)
            self.progress.parts_completed += 1
            logger.info(f"{part_name} partition write completed")
            return True
        except Exception as e:
            logger.error(f"Partition write failed for {part.part_type.value}: {e}")
            raise FlashVerificationError(
                f"Partition write failed for {part.part_type.value}: {e}"
            )

    async def _send_partition_start(self, partition_name: str, size: int) -> bool:
        try:
            name_bytes = partition_name.encode("utf-8")
            params = struct.pack("<H", len(name_bytes)) + name_bytes
            await self.usb.send_command(HeimdallProtocol.CMD_FILE_TRANSFER, params)
            return True
        except Exception as e:
            raise FlashVerificationError(f"Partition start failed: {e}")

    async def _write_block(self, block_data: bytes, offset: int, partition: str) -> bool:
        try:
            await self.usb.send_data(block_data)
            response = await self.usb.receive_data(4)
            if response[0] != HeimdallProtocol.RESP_SUCCESS:
                raise FlashVerificationError(
                    f"Block write verification failed for {partition} at offset {offset}"
                )
            return True
        except Exception as e:
            raise FlashVerificationError(f"Block write failed: {e}")

    async def _finalize_partition(self, partition_name: str, checksum: str) -> bool:
        try:
            checksum_bytes = bytes.fromhex(checksum[:32])
            params = struct.pack("<H", len(partition_name)) + partition_name.encode() + checksum_bytes
            response = await self.usb.send_command(HeimdallProtocol.CMD_STATUS, params)
            logger.info(f"{partition_name} partition finalized (checksum: {checksum[:16]}...)")
            return True
        except Exception as e:
            raise FlashVerificationError(f"Partition finalization failed: {e}")

    async def flash_all_partitions(self) -> bool:
        part_sequence = [
            FirmwarePartType.BL,
            FirmwarePartType.CP,
            FirmwarePartType.AP,
            FirmwarePartType.CSC,
        ]

        try:
            for part_type in part_sequence:
                if part_type not in self.firmware_parts:
                    logger.warning(f"Skipping {part_type.value}: not loaded")
                    continue

                part = self.firmware_parts[part_type]
                await self.write_firmware_part(part)
                await asyncio.sleep(0.5)

            logger.info("All partitions flashed successfully")
            return True
        except FlashVerificationError as e:
            logger.error(f"Partition flashing failed: {e}")
            raise FirmwareException(f"Partition flashing failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during partition flashing: {e}")
            raise FirmwareException(f"Unexpected error during partition flashing: {e}")

    async def verify_flash(self) -> bool:
        try:
            logger.info("Verifying flash completion...")
            response = await self.usb.receive_data(1)
            if response[0] == HeimdallProtocol.RESP_FLASH_START:
                logger.info("Flash verification successful")
                return True
            else:
                raise FlashVerificationError(
                    f"Flash verification failed: unexpected response {response[0]}"
                )
        except Exception as e:
            logger.error(f"Flash verification failed: {e}")
            raise FlashVerificationError(f"Flash verification failed: {e}")

    async def cleanup(self):
        try:
            logger.info("Cleaning up USB connection")
            await self.usb.disconnect()
            logger.info("USB disconnected")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

    async def execute_flash_pipeline(self, firmware_dir: Path) -> bool:
        start_time = time.time()
        try:
            logger.info("=== Samsung Firmware Flash Pipeline Starting ===")
            await self.load_firmware_images(firmware_dir)
            logger.info("Firmware images loaded successfully")

            await self.initialize_device()
            logger.info("Device initialized")

            await self.begin_flash_session()
            logger.info("Flash session established")

            await self.flash_all_partitions()
            logger.info("All partitions written")

            await self.verify_flash()
            logger.info("Flash verified")

            elapsed = time.time() - start_time
            logger.info(
                f"=== Flash Pipeline Complete ===\n"
                f"Total time: {elapsed:.2f}s\n"
                f"Data transferred: {self.progress.transferred_size / (1024*1024):.2f} MB\n"
                f"Average rate: {self.progress.transfer_rate_mbps:.2f} MB/s"
            )
            return True
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Flash pipeline failed after {elapsed:.2f}s: {e}")
            raise FirmwareException(f"Flash pipeline failed: {e}")
        finally:
            await self.cleanup()


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    firmware_directory = Path("/path/to/firmware")

    if not firmware_directory.exists():
        logger.error(f"Firmware directory not found: {firmware_directory}")
        return False

    try:
        flasher = FirmwareFlasher()
        result = await flasher.execute_flash_pipeline(firmware_directory)
        return result
    except FirmwareException as e:
        logger.error(f"Firmware flashing failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)
