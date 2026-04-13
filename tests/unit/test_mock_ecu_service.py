from tuner.domain.ecu_definition import EcuDefinition
from tuner.services.mock_ecu_service import MockEcuRuntime


def test_mock_runtime_uses_definition_channels() -> None:
    runtime = MockEcuRuntime(definition=EcuDefinition(name="demo", output_channels=["rpm", "map"]))

    snapshot = runtime.poll()

    assert [item.name for item in snapshot.values] == ["rpm", "map"]
    assert all(isinstance(item.value, float) for item in snapshot.values)
