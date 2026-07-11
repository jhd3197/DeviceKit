import os
import logging
import colorlog

from devicekit.tools import ToolsMixin
from devicekit.mixins.persistence import PersistenceMixin
from devicekit.mixins.adb import AdbMixin
from devicekit.mixins.cdp import CdpMixin
from devicekit.mixins.dynamodb import DynamodbMixin
from devicekit.mixins.aws_storage import AwsStorageMixin
from devicekit.mixins.uiautomator import Uiautomator2Mixin
from devicekit.mixins.events import EventsMixin
from devicekit.mixins.api_app import ApiAppMixin
from devicekit.mixins.queue import QueueMixin
from devicekit.mixins.alerts import AlertMixin
from devicekit.mixins.activity import ActivityMixin
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.profile import ProfileMixin
from devicekit.mixins.prompture_agent import PromptureAgentMixin
from devicekit.mixins.agent_gate import AgentGateMixin
from devicekit.mixins.nl_automation import NLAutomationMixin
from devicekit.mixins.fleet import FleetMixin
from devicekit.mixins.device_lock import DeviceLockMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.mixins.streaming import StreamingMixin
from devicekit.mixins.visual_regression import VisualRegressionMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.debug_bundle import DebugBundleMixin
from devicekit.mixins.agent_device import AgentDeviceMixin
from devicekit.mixins.pairing import PairingMixin
from devicekit.mixins.extensions import ExtensionsMixin
from devicekit.mixins.extension_ai import ExtensionAiMixin
from devicekit.mixins.jobs import JobsMixin
from devicekit.mixins.notifications import NotificationsMixin
from devicekit.mixins.metrics_history import MetricsHistoryMixin
from devicekit.mixins.settings import SettingsMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.api_keys import ApiKeysMixin


class Client(
    PersistenceMixin,
    AdbMixin,
    Uiautomator2Mixin,
    CdpMixin,
    DynamodbMixin,
    AwsStorageMixin,
    AutomationMixin,
    ProfileMixin,
    NLAutomationMixin,
    PromptureAgentMixin,
    AgentGateMixin,
    FleetMixin,
    FleetQueryMixin,
    DeviceLockMixin,
    StreamingMixin,
    VisualRegressionMixin,
    DebugBundleMixin,
    AgentDeviceMixin,
    PairingMixin,
    ExtensionsMixin,
    ExtensionAiMixin,
    JobsMixin,
    NotificationsMixin,
    MetricsHistoryMixin,
    SettingsMixin,
    IdentityMixin,
    ApiKeysMixin,
    EventsMixin,
    ApiAppMixin,
    QueueMixin,
    AlertMixin,
    ActivityMixin,
    AuthMixin,
    ToolsMixin,
):
    def __init__(self, device=None, local_port=9222, output_dir="output", logger_instance=None):
        super().__init__()
        self.device = device
        self.local_port = local_port
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # Bring up the persistence layer (engine + schema) before any data-owning
        # mixin touches the database.
        self.init_persistence()

        # Hydrate the in-memory agent-device registry from persisted rows.
        self.init_agent_registry()

        # Initialize the extension registries (blueprints load later, in build_app).
        self.init_extensions()

        # Register core job kinds and ensure the default system schedules exist. The consumer
        # and scheduler daemons start later, at server boot (build_app -> start_job_workers),
        # so imports and the test-suite never spawn threads.
        try:
            self.init_jobs()
        except Exception as e:
            logging.getLogger('devicekit').warning(f"Job system init skipped: {e}")

        # Seed the notification catalog and its retention schedule (after jobs so the prune
        # kind/schedule can register onto the live job system).
        try:
            self.init_notifications()
        except Exception as e:
            logging.getLogger('devicekit').warning(f"Notification bus init skipped: {e}")

        # Metrics history: register rollup/prune job kinds + schedules, seed default alert
        # rules, and register derived FQL fields (after jobs + notifications so both are live).
        try:
            self.init_metrics()
        except Exception as e:
            logging.getLogger('devicekit').warning(f"Metrics history init skipped: {e}")

        # Apply any persisted AI provider keys to the environment so Prompture picks them
        # up without a restart (plan 12 settings).
        try:
            self.init_settings()
        except Exception as e:
            logging.getLogger('devicekit').warning(f"Settings init skipped: {e}")

        # Configure authentication
        from config import API_KEY, AGENT_TOKENS
        self.configure_auth(API_KEY, AGENT_TOKENS)

        # Identity/RBAC substrate (plan 20): reset the user-count cache and optionally
        # bootstrap an admin from the environment. Solo mode (no users) is unchanged.
        try:
            self.init_identity()
        except Exception as e:
            logging.getLogger('devicekit').warning(f"Identity init skipped: {e}")

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
