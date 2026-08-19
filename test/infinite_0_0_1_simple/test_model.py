"""The Claude API seam: what the scaffold actually puts on the request."""

from types import SimpleNamespace

from infinite.config import NO_EFFORT, Config
from infinite.model import AnthropicModel


class Block(SimpleNamespace):
    def model_dump(self, mode="json"):
        return {"type": self.type, "text": getattr(self, "text", "")}


class FakeStream:
    """What `client.messages.stream(...)` returns: a context manager."""

    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeClient:
    """Records the kwargs of every `messages.stream` call."""

    def __init__(self):
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(
            SimpleNamespace(
                content=[Block(type="text", text="hi")],
                stop_reason="end_turn",
                usage=SimpleNamespace(model_dump=lambda mode="json": {"output_tokens": 1}),
            )
        )

    def only(self) -> dict:
        assert len(self.calls) == 1
        return self.calls[0]


def generate(config: Config, **overrides):
    client = FakeClient()
    AnthropicModel(config, client=client).generate(
        system="s", tools=[], messages=[{"role": "user", "content": "u"}],
        max_tokens=16, **overrides,
    )
    return client.only()


def test_a_step_sends_the_runs_model_effort_and_thinking():
    call = generate(Config(model="claude-opus-5", effort="high", thinking=True))

    assert call["model"] == "claude-opus-5"
    assert call["output_config"] == {"effort": "high"}
    assert call["thinking"] == {"type": "adaptive", "display": "summarized"}


def test_an_override_replaces_the_runs_setting():
    call = generate(Config(), model="claude-haiku-4-5", effort="low", thinking=False)

    assert call["model"] == "claude-haiku-4-5"
    assert call["output_config"] == {"effort": "low"}
    assert "thinking" not in call


def test_no_effort_sends_no_output_config_at_all():
    """The API's floor is `low`; below it there is only the absent parameter —
    which is also what the small models require, since they reject an effort."""
    call = generate(Config(), effort=NO_EFFORT)

    assert "output_config" not in call


def test_the_summariser_settings_are_that_by_default():
    config = Config()

    assert config.summary_effort == NO_EFFORT
    assert config.summary_model == "claude-haiku-4-5"
    assert config.summary_thinking is False


def test_the_system_message_is_marked_for_caching():
    call = generate(Config())

    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
