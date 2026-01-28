import os
import logging
import colorlog

from devicekit.tools import ToolsMixin
from devicekit.mixins.adb import AdbMixin
from devicekit.mixins.cdp import CdpMixin
from devicekit.mixins.dynamodb import DynamodbMixin
from devicekit.mixins.aws_storage import AwsStorageMixin
from devicekit.mixins.uiautomator import Uiautomator2Mixin
from devicekit.mixins.api_app import ApiAppMixin
from devicekit.mixins.queue import QueueMixin
from devicekit.mixins.alerts import AlertMixin
from devicekit.mixins.activity import ActivityMixin


class Client(
    AdbMixin,
    Uiautomator2Mixin,
    CdpMixin,
    DynamodbMixin,
    AwsStorageMixin,
    ApiAppMixin,
    QueueMixin,
    AlertMixin,
    ActivityMixin,
    ToolsMixin,
):
    def __init__(self, device=None, local_port=9222, output_dir="output", logger_instance=None):
        super().__init__()
        self.device = device
        self.local_port = local_port
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # Configure colored logging
        log = logging.getLogger('devicekit')
        log.setLevel(logging.INFO)
        log.handlers = []
        log.propagate = False

        handler = colorlog.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s[%(asctime)s] [%(levelname)s] - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
        handler.setFormatter(formatter)
        log.addHandler(handler)
        self.logger = log

        # Clean up Chrome on init if device is specified
        if device:
            try:
                self.stop_chrome(device=device)
                self.run_adb_command(["forward", "--remove-all"], device=device)
            except Exception:
                pass
