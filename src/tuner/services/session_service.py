from __future__ import annotations

from dataclasses import dataclass, field

from tuner.comms.interfaces import ControllerClient
from tuner.comms.mock_controller_client import MockControllerClient
from tuner.comms.protocol_client import ProtocolControllerClient
from tuner.comms.speeduino_controller_client import SpeeduinoControllerClient
from tuner.comms.xcp_controller_client import XcpControllerClient
from tuner.domain.connection import ConnectionConfig, ProtocolType, TransportType
from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.domain.session import SessionInfo, SessionState
from tuner.services.math_expression_evaluator import MathExpressionEvaluator
from tuner.transports.transport_factory import TransportFactory


@dataclass(slots=True)
class SessionService:
    transport_factory: TransportFactory
    definition: EcuDefinition | None = None
    client: ControllerClient | None = None
    info: SessionInfo = field(default_factory=SessionInfo)
    _prior_signature: str | None = field(default=None, init=False)
    _formula_evaluator: MathExpressionEvaluator = field(
        default_factory=MathExpressionEvaluator, init=False
    )

    def set_definition(self, definition: EcuDefinition | None) -> None:
        self.definition = definition
        if isinstance(self.client, MockControllerClient):
            self.client.set_definition(definition)

    def reconnect_signature_changed(self) -> bool:
        """True if the firmware signature changed compared to the session before this connect.

        Only meaningful immediately after a successful connect() call. Returns False
        if this is the first connection or if either signature was not available.
        Callers should surface a warning when this returns True — a signature change
        typically means a firmware reflash occurred and open tune/definition files
        should be re-validated before trusting staged edits or cached page data.
        """
        if self._prior_signature is None or self.info.firmware_signature is None:
            return False
        return self._prior_signature != self.info.firmware_signature

    @property
    def prior_firmware_signature(self) -> str | None:
        """The firmware signature captured before the most recent connect() call."""
        return self._prior_signature

    def connect(self, config: ConnectionConfig) -> SessionInfo:
        # Snapshot the signature from the previous session before disconnect clears state.
        self._prior_signature = self.info.firmware_signature
        self.disconnect()
        self.info.state = SessionState.CONNECTING
        self.info.transport_name = config.display_name()
        if config.transport == TransportType.MOCK:
            client = MockControllerClient(self.definition)
        else:
            transport = self.transport_factory.create(config)
            if config.protocol == ProtocolType.SIM_JSON:
                client = ProtocolControllerClient(transport=transport, definition=self.definition)
            elif config.protocol == ProtocolType.SPEEDUINO:
                client = SpeeduinoControllerClient(transport=transport, definition=self.definition)
            elif config.protocol == ProtocolType.XCP:
                client = XcpControllerClient(transport=transport, definition=self.definition)
            else:
                raise RuntimeError(f"Unsupported protocol: {config.protocol.value}")
        try:
            client.connect()
        except Exception as exc:
            try:
                client.disconnect()
            except Exception:
                pass
            self.client = None
            self.info.controller_name = None
            self.info.error_detail = str(exc) or exc.__class__.__name__
            self.info.state = SessionState.DISCONNECTED
            raise
        self.client = client
        self.info.state = SessionState.CONNECTED
        self.info.error_detail = None
        self.info.controller_name = getattr(client, "controller_name", None) or (
            self.definition.name if self.definition else "Unknown Controller"
        )
        self.info.firmware_capabilities = getattr(client, "capabilities", None)
        self.info.firmware_signature = getattr(client, "firmware_signature", None)
        return self.info

    def disconnect(self) -> SessionInfo:
        if self.client is not None:
            self.client.disconnect()
        self.client = None
        # Preserve firmware_signature so the next connect can detect a change.
        prior_signature = self.info.firmware_signature
        self.info = SessionInfo(
            project_name=self.info.project_name,
            controller_name=None,
            transport_name=None,
            firmware_capabilities=None,
            firmware_signature=prior_signature,
            error_detail=None,
            state=SessionState.DISCONNECTED,
        )
        return self.info

    def poll_runtime(self) -> OutputChannelSnapshot:
        if self.client is None:
            raise RuntimeError("No active session.")
        snapshot = self.client.read_runtime()
        # G4 sub-slice 86: enrich the raw hardware snapshot with any
        # formula-defined virtual output channels from the active
        # definition. No-op when the definition has no formulas, so this
        # adds zero overhead for legacy INIs that don't use them.
        return self._formula_evaluator.enrich_snapshot(snapshot, self.definition)

    def is_connected(self) -> bool:
        return self.info.state == SessionState.CONNECTED
