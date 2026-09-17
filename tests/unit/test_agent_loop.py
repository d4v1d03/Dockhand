"""Behavioural tests for run_agent against FakeLLM + FakeSandbox."""

from dockhand.agent.loop import (
    EV_ASK_USER,
    EV_ERROR,
    EV_MESSAGE,
    EV_TOOL_CALL,
    EV_TOOL_RESULT,
    EV_USAGE,
    Limits,
    run_agent,
)
from dockhand.agent.tools import default_registry
from dockhand.llm import FakeLLM, system_message, user_message
from dockhand.sandbox import FakeSandbox


class Recorder:
    def __init__(self):
        self.events = []

    def __call__(self, kind, payload):
        self.events.append((kind, payload))

    def kinds(self):
        return [k for k, _ in self.events]


def run(llm, sandbox=None, **kw):
    transcript = [system_message("sys"), user_message("do the thing")]
    rec = Recorder()
    outcome = run_agent(
        llm=llm,
        sandbox=sandbox or FakeSandbox(),
        transcript=transcript,
        tools=default_registry(),
        emit=rec,
        **kw,
    )
    return outcome, transcript, rec


def assert_transcript_valid(transcript):
    """Every assistant tool call is answered by exactly one tool message, in order."""
    pending = []
    for m in transcript:
        if m["role"] == "assistant":
            assert not pending, "new assistant turn while tool calls were unanswered"
            pending = [tc["id"] for tc in m.get("tool_calls", [])]
        elif m["role"] == "tool":
            assert pending and m["tool_call_id"] == pending.pop(0), "tool result out of order"
    assert not pending, f"dangling tool calls: {pending}"


def test_happy_path_explore_edit_test_finish():
    sb = FakeSandbox(files={"app.py": "x = 1\n"}, responses={"pytest": "1 passed\n"})
    llm = FakeLLM.script(
        FakeLLM.tool_call("list_files"),
        FakeLLM.tool_call("read_file", path="app.py"),
        FakeLLM.tool_call("write_file", path="app.py", content="x = 2\n"),
        FakeLLM.tool_call("bash", command="python -m pytest -q"),
        FakeLLM.tool_call("finish", summary="changed x to 2; tests pass"),
    )
    outcome, transcript, rec = run(llm, sb)
    assert outcome.status == "completed"
    assert outcome.summary == "changed x to 2; tests pass"
    assert outcome.steps == 5
    assert sb.read_file("app.py") == "x = 2\n"
    assert_transcript_valid(transcript)
    assert rec.kinds().count(EV_TOOL_CALL) == 5 and rec.kinds().count(EV_TOOL_RESULT) == 5
    assert rec.kinds().count(EV_USAGE) == 5
    # tool_call always precedes its tool_result
    assert rec.kinds().index(EV_TOOL_CALL) < rec.kinds().index(EV_TOOL_RESULT)


def test_text_without_tool_calls_completes():
    llm = FakeLLM.script(FakeLLM.text("All done, nothing to change."))
    outcome, transcript, rec = run(llm)
    assert outcome.status == "completed" and outcome.summary == "All done, nothing to change."
    assert (EV_MESSAGE, {"content": "All done, nothing to change."}) in rec.events
    assert transcript[-1]["role"] == "assistant"


def test_ask_user_pauses_with_question():
    llm = FakeLLM.script(FakeLLM.tool_call("ask_user", question="Postgres or SQLite?"))
    outcome, transcript, rec = run(llm)
    assert outcome.status == "waiting_for_user" and outcome.question == "Postgres or SQLite?"
    assert (EV_ASK_USER, {"question": "Postgres or SQLite?"}) in rec.events
    assert_transcript_valid(transcript)


def test_max_steps_fails_cleanly():
    llm = FakeLLM.script(*[FakeLLM.tool_call("bash", command="ls")] * 10)
    outcome, transcript, rec = run(llm, limits=Limits(max_steps=3))
    assert outcome.status == "failed" and outcome.steps == 3
    assert "max steps" in (outcome.error or "").lower()
    assert_transcript_valid(transcript)


def test_cancel_before_llm_call_and_between_tools():
    llm = FakeLLM.script(FakeLLM.tool_call("bash", command="ls"))
    outcome, _, _ = run(llm, should_cancel=lambda: True)
    assert outcome.status == "cancelled" and outcome.steps == 0

    calls = {"n": 0}

    def cancel_after_first_tool():
        calls["n"] += 1
        return calls["n"] > 2  # False for the llm check and the first tool, True after

    llm = FakeLLM.script(FakeLLM.tool_calls(("bash", {"command": "a"}), ("bash", {"command": "b"})))
    sb = FakeSandbox()
    outcome, transcript, _ = run(llm, sb, should_cancel=cancel_after_first_tool)
    assert outcome.status == "cancelled"
    assert sb.commands == ["a"]  # second tool never ran
    assert_transcript_valid(transcript)  # ...but its call was still answered


def test_unknown_tool_and_bad_args_are_reported_and_loop_continues():
    llm = FakeLLM.script(
        FakeLLM.tool_call("teleport", to="prod"),
        FakeLLM.tool_call("bash"),  # missing command
        FakeLLM.tool_call("finish", summary="ok"),
    )
    outcome, transcript, rec = run(llm)
    assert outcome.status == "completed" and outcome.steps == 3
    results = [p for k, p in rec.events if k == EV_TOOL_RESULT]
    assert results[0]["is_error"] and "unknown tool" in results[0]["output"]
    assert results[1]["is_error"] and "missing required" in results[1]["output"]
    assert_transcript_valid(transcript)


def test_llm_exception_becomes_failed_outcome():
    class Boom:
        model = "boom"

        def chat(self, messages, tools=None):
            raise RuntimeError("provider is down")

    outcome, transcript, rec = run(Boom())
    assert outcome.status == "failed" and "provider is down" in (outcome.error or "")
    assert any(k == EV_ERROR for k, _ in rec.events)


def test_multiple_tool_calls_in_one_turn_run_in_order():
    sb = FakeSandbox()
    llm = FakeLLM.script(
        FakeLLM.tool_calls(
            ("bash", {"command": "one"}), ("bash", {"command": "two"}), content="doing both"
        ),
        FakeLLM.tool_call("finish", summary="done"),
    )
    outcome, transcript, rec = run(llm, sb)
    assert sb.commands == ["one", "two"]
    assert (EV_MESSAGE, {"content": "doing both"}) in rec.events
    assert_transcript_valid(transcript)
    assert outcome.steps == 2
