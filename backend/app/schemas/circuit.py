"""Circuit schema 1.0. Cross-object integrity lives in circuit_engine."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.common import Contract, Identifier, PositiveNumber

PinName = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
PinReference = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}\.[A-Za-z0-9_-]{1,32}$")]


class Component(Contract):
    id: Identifier
    type: Literal["resistor", "led", "push_button", "jumper", "supply_terminal"]
    pins: Annotated[list[PinName], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def check_pins(self) -> "Component":
        expected = {
            "resistor": {"1", "2"},
            "led": {"anode", "cathode"},
            "push_button": {"1", "2", "3", "4"},
            "jumper": {"1", "2"},
            "supply_terminal": {"positive", "negative"},
        }[self.type]
        if len(self.pins) != len(expected) or set(self.pins) != expected:
            raise ValueError(f"pins must be exactly {sorted(expected)}")
        return self


class Resistor(Component):
    type: Literal["resistor"]
    value_ohms: PositiveNumber


class LED(Component):
    type: Literal["led"]


class PushButton(Component):
    """Normally-open momentary button; internal contact model is deferred to M2."""

    type: Literal["push_button"]


class Jumper(Component):
    type: Literal["jumper"]


class SupplyTerminal(Component):
    type: Literal["supply_terminal"]


ComponentSpec = Annotated[
    Resistor | LED | PushButton | Jumper | SupplyTerminal, Field(discriminator="type")
]


class Net(Contract):
    id: Identifier
    members: Annotated[list[PinReference], Field(min_length=1, max_length=128)]
    role: Literal["power", "ground", "signal"] = "signal"


class Supply(Contract):
    # Conservative product envelope, not an electrical safety certification.
    voltage_v: Annotated[float, Field(gt=0, le=12, allow_inf_nan=False)]
    current_limit_ma: Annotated[float, Field(gt=0, le=500, allow_inf_nan=False)]
    positive_net: Identifier
    negative_net: Identifier


class Circuit(Contract):
    schema_version: Literal["1.0"]
    name: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
    units: Literal["SI"] = "SI"
    assumptions: Annotated[list[Annotated[str, Field(max_length=500)]], Field(max_length=32)] = (
        Field(default_factory=list)
    )
    components: Annotated[list[ComponentSpec], Field(min_length=1, max_length=64)]
    nets: Annotated[list[Net], Field(min_length=1, max_length=128)]
    supply: Supply | None = None
