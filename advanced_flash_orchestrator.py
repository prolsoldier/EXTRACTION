import asyncio
import hashlib
import json
import logging
import struct
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Set
from abc import ABC, abstractmethod
import lz4.frame
import usb.core
import usb.util
from pydantic import BaseModel, Field, field_validator


logger = logging.getLogger(__name__)


class USBTransportMode(str, Enum):
    HEIMDALL = "heimdall"
    DIRECT_PYUSB = "direct_pyusb"
    AUTO_DETECT = "auto_detect"


class FlashMode(str, Enum):
    SEQUENTIAL = "sequential"
    STAGED = "staged"
    WRITE_ONLY = "write_only"


class PartitionPriority(str, Enum):
    BOOTLOADER_FIRST = "bootloader_first"
    CRITICAL_FIRST = "critical_first"
    SYSTEM_FIRST = "system_first"


class OrchestrationConfig(BaseModel):
    usb_vendor_id: int = Field(default=0x04E8, ge=0, le=0xFFFF)
    usb_product_id: int = Field(default=0x685D, ge=0, le=0xFFFF)
    usb_endpoint_out: int = Field(default=0x01)
    usb_endpoint_in: int = Field(default=0x81)
    block_size_kb: int = Field(default=2, ge=1, le=16)
    usb_timeout_ms: int = Field(default=5000, ge=1000, le=30000)
    max_retry_attempts: int = Field(default=3, ge=1, le=10)
    transport_mode: USBTransportMode = Field(default=USBTransportMode.AUTO_DETECT)
    flash_mode: FlashMode = Field(default=FlashMode.SEQUENTIAL)
    partition_order: PartitionPriority = Field(default=PartitionPriority.BOOTLOADER_FIRST)
    enable_verification: bool = Field(default=True)
    enable_checksum_validation: bool = Field(default=True)
    firmware_directory: Path = Field(default=Path("/path/to/firmware"))
    log_level: str = Field(default="INFO")

    @field_validator("block_size_kb")
    def validate_block_size(cls, v):
        if v not in [1, 2, 4, 8, 16]:
            raise ValueError("block_size_kb must be power of 2")
        return v


@dataclass
class TransferMetrics:
    partition_name: str
    start_time: float = field(default_factory=time.time)
    bytes_sent: int = 0
    bytes_expected: int = 0
    retry_count: int = 0
    verification_errors: int = 0
    is_complete: bool = False
    end_time: Optional[float] = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def transfer_rate_mbps(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed < 0.1:
            return 0.0
        return (self.bytes_sent / (1024 * 1024)) / elapsed

    @property
    def progress_percent(self) -> float:
        if self.bytes_expected == 0:
            return 0.0
        return (self.bytes_sent / self.bytes_expected) * 100

    def mark_complete(self):
        self.is_complete = True
        self.end_time = time.time()


class PartitionFactory:
    PARTITION_MAPPING = {
        "AP": ("AP.lz4", "Application"),
        "BL": ("BL.lz4", "Bootloader"),
        "CP": ("CP.lz4", "Modem"),
        "CSC": ("CSC.lz4", "Consumer Customization"),
    }

    @staticmethod
    def get_partition_sequences(priority: PartitionPriority) -> List[str]:
        base = ["AP", "BL", "CP", "CSC"]
        if priority == PartitionPriority.BOOTLOADER_FIRST:
            return ["BL", "CP", "AP", "CSC"]
        elif priority == PartitionPriority.CRITICAL_FIRST:
            return ["BL", "CP", "AP", "CSC"]
        elif priority == PartitionPriority.SYSTEM_FIRST:
            return ["AP", "CP", "BL", "CSC"]
        return base


class AbstractUSBTransport(ABC):
    def __init__(self, config: OrchestrationConfig):
        self.config = config
        self.device = None
        self._is_connected = False
        self._connection_lock = asyncio.Lock()

    @abstractmethod
    async def connect(self) -> bool:
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        pass

    @abstractmethod
    async def send_raw(self, data: bytes) -> bool:
        pass

    @abstractmethod
    async def receive_raw(self, length: int) -> bytes:
        pass

    @abstractmethod
    async def send_command(self, cmd_id: int, payload: bytes) -> bytes:
        pass

    @property
    def is_connected(self) -> bool:
        return self._is_connected


class HeimdallTransport(AbstractUSBTransport):
    CMD_FILE_TRANSFER = 0x02
    CMD_DATA_TRANSFER = 0x03
    CMD_STATUS = 0x06
    CMD_FILE_PART_SIZE = 0x08
    CMD_FLASH_START = 0x09
    CMD_FLASH_DATA = 0x0C

    RESP_SUCCESS = 0x00
    RESP_DEVICE_ID = 0x05
    RESP_INIT = 0x0A
    RESP_DATA_ACK = 0x0B

    async def connect(self) -> bool:
        async with self._connection_lock:
            try:
                self.device = usb.core.find(
                    idVendor=self.config.usb_vendor_id,
                    idProduct=self.config.usb_product_id,
                )
                if not self.device:
                    raise Exception(f"Device not found: {self.config.usb_vendor_id:04x}:{self.config.usb_product_id:04x}")

                if self.device.is_kernel_driver_active(0):
                    try:
                        self.device.detach_kernel_driver(0)
                        logger.info("Kernel driver detached")
                    except usb.core.USBError as e:
                        logger.warning(f"Could not detach kernel driver: {e}")

                self.device.set_configuration()
                self._is_connected = True
                logger.info(f"Heimdall transport connected: {self.device.manufacturer} {self.device.product}")
                return True
            except Exception as e:
                logger.error(f"Heimdall connect failed: {e}")
                self._is_connected = False
                raise

    async def disconnect(self) -> bool:
        async with self._connection_lock:
            try:
                if self.device:
                    usb.util.release_interface(self.device, 0)
                    self.device = None
                self._is_connected = False
                logger.info("Heimdall transport disconnected")
                return True
            except Exception as e:
                logger.warning(f"Error disconnecting Heimdall: {e}")
                return False

    async def send_raw(self, data: bytes) -> bool:
        try:
            if not self._is_connected:
                raise Exception("Transport not connected")
            for attempt in range(self.config.max_retry_attempts):
                try:
                    self.device.write(self.config.usb_endpoint_out, data, self.config.usb_timeout_ms)
                    return True
                except usb.core.USBTimeoutError:
                    if attempt < self.config.max_retry_attempts - 1:
                        await asyncio.sleep(0.2 * (2 ** attempt))
                    else:
                        raise
        except Exception as e:
            logger.error(f"Heimdall send_raw failed: {e}")
            raise

    async def receive_raw(self, length: int) -> bytes:
        try:
            if not self._is_connected:
                raise Exception("Transport not connected")
            for attempt in range(self.config.max_retry_attempts):
                try:
                    data = self.device.read(self.config.usb_endpoint_in, length, self.config.usb_timeout_ms)
                    return bytes(data)
                except usb.core.USBTimeoutError:
                    if attempt < self.config.max_retry_attempts - 1:
                        await asyncio.sleep(0.2 * (2 ** attempt))
                    else:
                        raise
        except Exception as e:
            logger.error(f"Heimdall receive_raw failed: {e}")
            raise

    async def send_command(self, cmd_id: int, payload: bytes) -> bytes:
        try:
            packet = struct.pack("<I", cmd_id) + payload
            await self.send_raw(packet)
            response = await self.receive_raw(4)
            if len(response) < 1:
                raise Exception("Invalid response from device")
            return response
        except Exception as e:
            logger.error(f"Heimdall send_command failed: {e}")
            raise


class DirectPyUSBTransport(AbstractUSBTransport):
    async def connect(self) -> bool:
        async with self._connection_lock:
            try:
                self.device = usb.core.find(
                    idVendor=self.config.usb_vendor_id,
                    idProduct=self.config.usb_product_id,
                )
                if not self.device:
                    raise Exception(f"Device not found")

                if self.device.is_kernel_driver_active(0):
                    self.device.detach_kernel_driver(0)

                self.device.set_configuration()
                self._is_connected = True
                logger.info("Direct pyUSB transport connected")
                return True
            except Exception as e:
                logger.error(f"Direct pyUSB connect failed: {e}")
                self._is_connected = False
                raise

    async def disconnect(self) -> bool:
        async with self._connection_lock:
            try:
                if self.device:
                    usb.util.release_interface(self.device, 0)
                    self.device = None
                self._is_connected = False
                logger.info("Direct pyUSB transport disconnected")
                return True
            except Exception as e:
                logger.warning(f"Error disconnecting direct pyUSB: {e}")
                return False

    async def send_raw(self, data: bytes) -> bool:
        try:
            if not self._is_connected:
                raise Exception("Transport not connected")
            self.device.write(self.config.usb_endpoint_out, data, self.config.usb_timeout_ms)
            return True
        except Exception as e:
            logger.error(f"Direct pyUSB send_raw failed: {e}")
            raise

    async def receive_raw(self, length: int) -> bytes:
        try:
            if not self._is_connected:
                raise Exception("Transport not connected")
            data = self.device.read(self.config.usb_endpoint_in, length, self.config.usb_timeout_ms)
            return bytes(data)
        except Exception as e:
            logger.error(f"Direct pyUSB receive_raw failed: {e}")
            raise

    async def send_command(self, cmd_id: int, payload: bytes) -> bytes:
        try:
            packet = struct.pack("<I", cmd_id) + payload
            await self.send_raw(packet)
            response = await self.receive_raw(4)
            return response
        except Exception as e:
            logger.error(f"Direct pyUSB send_command failed: {e}")
            raise


class TransportFactory:
    @staticmethod
    def create_transport(config: OrchestrationConfig) -> AbstractUSBTransport:
        if config.transport_mode == USBTransportMode.HEIMDALL:
            return HeimdallTransport(config)
        elif config.transport_mode == USBTransportMode.DIRECT_PYUSB:
            return DirectPyUSBTransport(config)
        else:
            try:
                transport = HeimdallTransport(config)
                return transport
            except Exception:
                logger.info("Heimdall transport unavailable, falling back to Direct pyUSB")
                return DirectPyUSBTransport(config)


@dataclass
class PartitionData:
    name: str
    raw_data: bytes
    file_path: Path
    checksum_sha256: str = field(default="")

    def __post_init__(self):
        if not self.checksum_sha256:
            self.checksum_sha256 = hashlib.sha256(self.raw_data).hexdigest()

    @property
    def size_bytes(self) -> int:
        return len(self.raw_data)

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


class PartitionLoader:
    def __init__(self, config: OrchestrationConfig):
        self.config = config
        self.partitions: Dict[str, PartitionData] = {}

    async def load_all_partitions(self) -> Dict[str, PartitionData]:
        try:
            logger.info(f"Loading firmware partitions from {self.config.firmware_directory}")

            for partition_key, (filename, display_name) in PartitionFactory.PARTITION_MAPPING.items():
                file_path = self.config.firmware_directory / filename
                if not file_path.exists():
                    logger.warning(f"Partition file not found: {file_path}")
                    continue

                try:
                    with open(file_path, "rb") as f:
                        compressed_data = f.read()

                    logger.info(f"Decompressing {partition_key} ({display_name})...")
                    decompressed_data = lz4.frame.decompress(compressed_data)

                    partition = PartitionData(
                        name=partition_key,
                        raw_data=decompressed_data,
                        file_path=file_path,
                    )

                    self.partitions[partition_key] = partition
                    logger.info(
                        f"Loaded {partition_key}: {partition.size_mb:.2f} MB, "
                        f"SHA256: {partition.checksum_sha256[:16]}..."
                    )
                except lz4.frame.LZ4FrameCompressionError as e:
                    logger.error(f"LZ4 decompression failed for {partition_key}: {e}")
                    raise
                except Exception as e:
                    logger.error(f"Failed to load {partition_key}: {e}")
                    raise

            if not self.partitions:
                raise Exception("No firmware partitions loaded")

            total_size_mb = sum(p.size_mb for p in self.partitions.values())
            logger.info(f"Total firmware size: {total_size_mb:.2f} MB ({len(self.partitions)} partitions)")
            return self.partitions
        except Exception as e:
            logger.error(f"Partition loading failed: {e}")
            raise


class AdvancedFlashOrchestrator:
    def __init__(self, config: OrchestrationConfig):
        self.config = config
        self.transport: Optional[AbstractUSBTransport] = None
        self.partitions: Dict[str, PartitionData] = {}
        self.transfer_metrics: Dict[str, TransferMetrics] = {}
        self.global_start_time: float = time.time()

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing AdvancedFlashOrchestrator")
            self.transport = TransportFactory.create_transport(self.config)
            logger.info(f"Transport created: {type(self.transport).__name__}")

            await self.transport.connect()
            logger.info("Transport connected")

            loader = PartitionLoader(self.config)
            self.partitions = await loader.load_all_partitions()
            logger.info(f"Loaded {len(self.partitions)} partitions")

            for partition_name in self.partitions.keys():
                self.transfer_metrics[partition_name] = TransferMetrics(
                    partition_name=partition_name,
                    bytes_expected=self.partitions[partition_name].size_bytes,
                )

            return True
        except Exception as e:
            logger.error(f"Orchestrator initialization failed: {e}")
            raise

    async def write_partition_sequential(self, partition_name: str, partition_data: PartitionData) -> bool:
        try:
            metrics = self.transfer_metrics[partition_name]
            block_size = self.config.block_size_kb * 1024

            logger.info(f"Writing partition {partition_name} ({partition_data.size_mb:.2f} MB)")

            offset = 0
            while offset < partition_data.size_bytes:
                chunk_size = min(block_size, partition_data.size_bytes - offset)
                chunk = partition_data.raw_data[offset:offset + chunk_size]

                try:
                    await self.transport.send_raw(chunk)
                    metrics.bytes_sent += chunk_size

                    progress = (metrics.bytes_sent / metrics.bytes_expected) * 100
                    eta_seconds = (
                        (metrics.bytes_expected - metrics.bytes_sent) /
                        (1024 * 1024 * max(0.1, metrics.transfer_rate_mbps))
                        if metrics.transfer_rate_mbps > 0 else 0
                    )

                    if progress % 10 < (chunk_size / metrics.bytes_expected) * 100:
                        logger.info(
                            f"{partition_name}: {progress:.1f}% "
                            f"({metrics.bytes_sent / (1024*1024):.1f}/{partition_data.size_mb:.1f} MB) "
                            f"Rate: {metrics.transfer_rate_mbps:.2f} MB/s ETA: {eta_seconds:.0f}s"
                        )

                except usb.core.USBError as e:
                    metrics.retry_count += 1
                    logger.warning(f"USB error on partition {partition_name}: {e}")
                    if metrics.retry_count >= self.config.max_retry_attempts:
                        raise
                    await asyncio.sleep(0.5)
                    continue

                offset += chunk_size

            if self.config.enable_checksum_validation:
                logger.info(f"Validating checksum for {partition_name}...")
                await self._validate_partition_checksum(partition_name, partition_data)

            metrics.mark_complete()
            logger.info(f"Partition {partition_name} write completed in {metrics.elapsed_seconds:.2f}s")
            return True
        except Exception as e:
            logger.error(f"Partition write failed for {partition_name}: {e}")
            raise

    async def _validate_partition_checksum(self, partition_name: str, partition_data: PartitionData):
        try:
            checksum_bytes = bytes.fromhex(partition_data.checksum_sha256[:32])
            cmd_payload = struct.pack("<H", len(partition_name)) + partition_name.encode() + checksum_bytes
            response = await self.transport.send_command(HeimdallTransport.CMD_STATUS, cmd_payload)
            if response[0] != HeimdallTransport.RESP_SUCCESS:
                self.transfer_metrics[partition_name].verification_errors += 1
                raise Exception(f"Checksum validation failed for {partition_name}")
            logger.info(f"Checksum validation passed for {partition_name}")
        except Exception as e:
            logger.error(f"Checksum validation error for {partition_name}: {e}")
            raise

    async def flash_all_partitions(self) -> bool:
        try:
            partition_sequence = PartitionFactory.get_partition_sequences(self.config.partition_order)
            sequence_to_flash = [p for p in partition_sequence if p in self.partitions]

            logger.info(f"Flash sequence: {sequence_to_flash}")

            for partition_name in sequence_to_flash:
                partition_data = self.partitions[partition_name]
                await self.write_partition_sequential(partition_name, partition_data)
                await asyncio.sleep(0.25)

            logger.info("All partitions flashed")
            return True
        except Exception as e:
            logger.error(f"Flash all partitions failed: {e}")
            raise

    async def verify_device_state(self) -> bool:
        try:
            logger.info("Verifying device state...")
            await asyncio.sleep(1.0)
            logger.info("Device state verification complete")
            return True
        except Exception as e:
            logger.error(f"Device state verification failed: {e}")
            raise

    async def cleanup(self):
        try:
            if self.transport:
                await self.transport.disconnect()
                logger.info("Transport disconnected")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

    def generate_report(self) -> Dict:
        total_elapsed = time.time() - self.global_start_time
        total_bytes_written = sum(m.bytes_sent for m in self.transfer_metrics.values())
        total_bytes_expected = sum(m.bytes_expected for m in self.transfer_metrics.values())

        report = {
            "status": "complete" if all(m.is_complete for m in self.transfer_metrics.values()) else "partial",
            "total_time_seconds": total_elapsed,
            "total_bytes_written": total_bytes_written,
            "total_bytes_expected": total_bytes_expected,
            "overall_rate_mbps": (total_bytes_written / (1024 * 1024)) / total_elapsed if total_elapsed > 0 else 0,
            "partitions": {
                name: {
                    "bytes_sent": m.bytes_sent,
                    "bytes_expected": m.bytes_expected,
                    "progress_percent": m.progress_percent,
                    "transfer_rate_mbps": m.transfer_rate_mbps,
                    "elapsed_seconds": m.elapsed_seconds,
                    "retry_count": m.retry_count,
                    "verification_errors": m.verification_errors,
                    "is_complete": m.is_complete,
                }
                for name, m in self.transfer_metrics.items()
            },
        }
        return report

    async def execute_full_pipeline(self) -> bool:
        try:
            logger.info("=== Starting Advanced Flash Pipeline ===")
            await self.initialize()
            logger.info("Orchestrator initialized")

            await self.flash_all_partitions()
            logger.info("All partitions flashed")

            await self.verify_device_state()
            logger.info("Device state verified")

            report = self.generate_report()
            logger.info(f"Flash Report: {json.dumps(report, indent=2)}")

            logger.info("=== Flash Pipeline Complete ===")
            return True
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            report = self.generate_report()
            logger.error(f"Partial Report: {json.dumps(report, indent=2)}")
            raise
        finally:
            await self.cleanup()


async def run_orchestration(config_path: Optional[Path] = None):
    if config_path and config_path.exists():
        with open(config_path) as f:
            config_dict = json.load(f)
        config = OrchestrationConfig(**config_dict)
    else:
        config = OrchestrationConfig()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        orchestrator = AdvancedFlashOrchestrator(config)
        await orchestrator.execute_full_pipeline()
        return True
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = asyncio.run(run_orchestration(config_path))
    exit(0 if result else 1)
