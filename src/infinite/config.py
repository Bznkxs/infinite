"""Configuration for the 0.0.7f-simple scaffold.

In the simple scaffold every dynamic part of the context is a register, and the
canvas is just a register with a larger length limit. There are three length
tiers: normal registers, the wide special registers, and the canvas.
"""

from dataclasses import dataclass

#: An effort of `"none"` means *send no effort at all* — the request carries no
#: `output_config`. The API's own floor is `low`, so this is the only way below
#: it, and the cheap models are the reason it exists: a small model rejects the
#: effort parameter outright rather than ignoring it.
NO_EFFORT = "none"

#: Characters per token, for sizing one generation before it is made. Measured
#: over the 580 steps of the 0.0.7f run — the whole request came to 2.83 chars a
#: token and the dump alone to 2.53 — and again against 0.0.7g's compressed
#: prose, where the fixed half is 2.64 and the dump 2.68. The estimate has to
#: err high to be worth having, so it uses the densest of them.
CHARS_PER_TOKEN = 2.6

#: Points at the result file (or status / error message) of the last ONE tool call.
RESULT_REGISTER = 0
#: "True" when the previous generation was cut off mid-way, "False" otherwise.
TRUNCATION_REGISTER = 1
#: The agent's own statement of what it is trying to do. Only `set_target`
#: writes it, and it survives every step until the agent replaces it.
TARGET_REGISTER = 2
#: The whole of the last step: what the agent thought, then what it did.
STEP_REGISTER = 3
#: A running summary of everything before the last step, rewritten after every
#: step by a summariser sub-agent.
SUMMARY_REGISTER = 4

#: The special registers that hold prose rather than a flag or a path, and so
#: get their own, larger, length limit.
WIDE_REGISTERS = (TARGET_REGISTER, STEP_REGISTER, SUMMARY_REGISTER)

#: How register 3 is laid out. Each half is cut to its own budget and labelled,
#: so the register's limit is both halves plus the labels — never less than what
#: was promised for either half.
STEP_THINKING_LABEL = "[thinking]\n"
STEP_ACTION_LABEL = "\n[action]\n"
STEP_LABEL_LENGTH = len(STEP_THINKING_LABEL) + len(STEP_ACTION_LABEL)

#: What the special registers mean, as a version. Register values are restored
#: by index on resume, so a run recorded under a different layout cannot simply
#: continue: bumped by 0.0.3 (2 specials -> 5) and again by 0.0.4 (thinking and
#: action merged into 3; 4 became the summary). 0.0.5 changed *who* writes
#: register 4 and 0.0.6 changed what that writer costs — neither changed what
#: the register holds, so the layout is unchanged and a 0.0.4 or 0.0.5 run
#: resumes into this scaffold without an upgrade.
REGISTER_LAYOUT = 4

#: Shown in the register dump so the agent does not have to remember what each
#: special register is for.
REGISTER_NAMES = {
    RESULT_REGISTER: "last result",
    TRUNCATION_REGISTER: "cut off?",
    TARGET_REGISTER: "target",
    STEP_REGISTER: "last step",
    SUMMARY_REGISTER: "summary",
}


@dataclass(frozen=True)
class Config:
    # Model
    model: str = "claude-opus-5"
    effort: str = "high"
    thinking: bool = True

    #: Workspace: how much the model may generate in one step. 0.0.7a doubled it
    #: from 8192: the modules a reconstruction has to write run to 200-350 lines,
    #: which is most of an 8192-token step once thinking is paid for, so a step
    #: that should write one file wrote part of one.
    workspace_tokens: int = 16384

    # Registers
    num_registers: int = 33
    num_special_registers: int = 5
    #: 0.0.7b raised this from 512. A `sed` of a source file is thousands of
    #: chars; at 512 the agent saw a tenth of what it asked for, and 0.0.7a's run
    #: spent 435 steps re-reading rather than noticing.
    max_register_length: int = 1024
    #: For register 4, and for register 2 unless `max_target_length` says
    #: otherwise. Holds prose the agent reads back. 0.0.7b
    #: raised it from 4096: the summariser writes what the material needs
    #: (4100-5000 chars, whatever budget it is given), so at 4096 more than half
    #: of 0.0.7a's steps bought a second generation to get under it.
    max_special_length: int = 6144
    #: Register 2 alone, when the target should not cost what the summary
    #: costs. They are the same tier and different problems: the agent writes
    #: its target and can be brief on purpose, while the summariser writes what
    #: the material needs and cannot hit a length by generating (0.0.5). At a
    #: small context that difference is worth 768 characters. None means the
    #: two share `max_special_length`, which is what every version before
    #: 0.0.7g did.
    max_target_length: int | None = None
    #: Each half of register 3 — the last thinking, and the last action.
    max_step_half_length: int = 2048
    max_canvas_length: int = 20000
    #: What the special registers mean; see REGISTER_LAYOUT. Not a setting to
    #: change — it is recorded so a resume can tell one layout from another.
    register_layout: int = REGISTER_LAYOUT

    # The summary in register 4: after every step one tool-less model call
    # rewrites it from the previous summary and that step. It is a generation,
    # not an agent — no registers, no trajectory, no tools, no second step.
    summary: bool = True
    #: The length the summariser is given as its budget. It is the only length
    #: it is told: register 4's real limit is the scaffold's business, and a
    #: model that knows the ceiling writes to the ceiling. The gap between the
    #: two is the headroom that makes the ordinary overshoot free. 0.0.6 ran
    #: this at 3000 against a 4096 register and still bought a retry on a
    #: quarter of steps, the median first attempt landing at 3570; 0.0.7a asks
    #: for less so the ordinary overshoot lands inside the register.
    summary_target_chars: int = 2400
    #: Whole generations to spend getting under the register's limit. Each
    #: retry is a fresh generation shown the attempt that was too long; after
    #: the last one the scaffold truncates rather than losing the summary.
    summary_max_attempts: int = 3
    #: The summariser rewrites a paragraph, so it runs on the cheap model and
    #: with no effort at all. `summary_model` of None means the run's model.
    summary_model: str | None = "claude-haiku-4-5"
    summary_effort: str = NO_EFFORT
    summary_thinking: bool = False
    summary_max_tokens: int = 2048

    # Loop / recursion budgets. max_steps is per run segment: a resumed run
    # gets a fresh allowance. None means no cap.
    max_steps: int | None = 40
    #: The deepest `spawn` may go, as an absolute depth: an agent at `depth`
    #: may spawn while `depth < max_depth`. None means the scaffold has no
    #: opinion, which is 0.0.8c's position — a ceiling is a property of the
    #: subtree and only the agent standing in it knows anything about the
    #: subtree. 0.0.7a set it to 1 because deep trees serialise and every level
    #: paid to brief the next; the second is what the structured brief is for,
    #: and the first is a resource cost that `charge_children` now prices. It
    #: stays settable because a user is a parent and should get what a parent
    #: gets — an experiment can still pin it.
    max_depth: int | None = None
    #: A child's steps come out of its parent's remaining budget (0.0.8c §5).
    #: Without this a parent's counter moves by one however many steps its child
    #: spends, so commissioning a hundred-step digest and running one `grep`
    #: cost the same. False restores 0.0.7j's accounting, for measuring the
    #: difference.
    charge_children: bool = True
    #: How many children of one step may run at the same time. 0.0.7f made a
    #: step's `spawn` calls concurrent — they were asked for together, and the
    #: scaffold ran them one after another — but a root that fans out five ways
    #: also puts five agents and five summarisers on the API at once, which
    #: 0.0.7c already named as part of why it pushed back. This is the ceiling.
    spawn_workers: int = 4

    #: A step's own generation is the one call the scaffold cannot do without, and
    #: until 0.0.7c it was the only failure that was fatal: a tool error goes to
    #: register 0, a summariser error leaves the old summary standing, but a
    #: transient API error on the step itself raised out of the loop and killed
    #: the run. This is the scaffold's own patience, on top of the SDK's retries,
    #: and it is a budget of *time* rather than of attempts: an overload that
    #: lasted minutes beat 0.0.7c's first shape (4 attempts, 5-10-20s = 35s) on
    #: the very first step of a run. A scaffold built for long runs should wait
    #: out a transient outage rather than end a segment over it.
    step_retry_seconds: float = 900.0
    #: Seconds before the second attempt; doubled for each one after it, capped.
    step_retry_backoff: float = 5.0
    step_retry_backoff_max: float = 60.0
    #: Passed to the Anthropic client, which retries 429/5xx/529 itself.
    api_max_retries: int = 8

    #: A ceiling on one whole generation — everything the model is sent plus
    #: everything it may generate — refused at construction rather than
    #: discovered in a bill. None means no ceiling, which is what every version
    #: through 0.0.7f had: the registers grew from 0.0.6's 47KB to 66KB and the
    #: output cap doubled, and nothing anywhere added the two up. 0.0.7f-short
    #: is the configuration that sets it (10000) and fits under it.
    max_context_tokens: int | None = None

    # Tool limits
    bash_timeout: float = 60.0
    max_load_bytes: int = 20 * 1024 * 1024
    #: 0.0.8a §3: the register file is synced to `$REGDIR/0 … $REGDIR/N` and
    #: `$R0 … $RN` around every `bash` call, so a value can move from a register
    #: into a command, into another register, or out of a computation without
    #: passing through a generation. False is 0.0.7's behaviour, for measuring
    #: what transit actually costs.
    registers_as_files: bool = True
    #: 7.1: `lookup(symbol)` over an index the scaffold maintains, so forty
    #: facts cost forty lines rather than forty pages.
    lookup: bool = True
    #: How many index lines one `lookup` may return.
    lookup_max_matches: int = 24
    #: 0.0.8c §3: the scaffold runs a child's `check` command when the child
    #: writes its response, and a response that fails it is refused. False
    #: makes `check` advisory, for measuring what enforcing it buys.
    run_checks: bool = True
    #: Seconds a `check` command may take before it is called failed.
    check_timeout: float = 300.0

    # Firewall: writes are always confined to the workspace; these are the
    # extra directories the agent may *read*. Empty means workspace-only.
    firewall: bool = True
    readable_dirs: tuple[str, ...] = ()

    @property
    def dump_chars(self) -> int:
        """The largest register dump this geometry can produce.

        Every register at its limit, plus the header line each one always emits
        and the `[Step]` line above them. It is an upper bound the scaffold
        enforces, not an average: what a step actually sends is this or less.
        """
        content = sum(self.register_limit(i) for i in range(self.num_registers))
        # `--- register 10 (2560/2560 chars; canvas) ---` and a newline, plus
        # `[Registers]` and the `[Step]` line at its longest — depth, the step
        # counter, what children have debited, the run-wide total and the
        # last-steps warning, all at once.
        return content + 56 * self.num_registers + 260

    @property
    def working_set_chars(self) -> int:
        """What the *agent* controls, which is the number 7.4 asks to be reported.

        The free registers, the canvas, and the target — every place a value the
        agent chose can sit. Registers 0, 1, 3 and 4 are written by the system
        and are not memory the agent can commit against, so they are not counted
        even though the model pays for them. At 0.0.7g this came to 3,280 chars
        against a request of 7,453 tokens: the scaffold explaining itself was
        43% of it and the agent had 16%.
        """
        free = sum(
            self.register_limit(i)
            for i in range(self.num_special_registers, self.num_registers)
        )
        return free + self.register_limit(TARGET_REGISTER)

    def context_tokens(self, fixed_chars: int) -> dict[str, int]:
        """How big one generation can get, given the unchanging half of it.

        `fixed_chars` is the system message and the tool schemas — the part that
        is identical every step. The answer is what the model may be sent at its
        fullest plus what it may generate, which is the number a run is actually
        bought by.
        """
        chars = fixed_chars + self.dump_chars
        input_tokens = int(chars / CHARS_PER_TOKEN)
        working_set = self.working_set_chars
        return {
            "fixed_chars": fixed_chars,
            "dump_chars": self.dump_chars,
            "input_tokens": input_tokens,
            "output_tokens": self.workspace_tokens,
            "total_tokens": input_tokens + self.workspace_tokens,
            # 7.4: "it should be reported as *usable working set*, not just
            # total". A scaffold that grows its own prose to buy the agent room
            # should have to show both numbers next to each other.
            "working_set_chars": working_set,
            "working_set_tokens": int(working_set / CHARS_PER_TOKEN),
        }

    @property
    def canvas_id(self) -> int:
        """The canvas is the last register."""
        return self.num_registers - 1

    @property
    def target_id(self) -> int:
        return TARGET_REGISTER

    @property
    def step_register_limit(self) -> int:
        """Both halves of register 3, plus the labels that separate them."""
        return 2 * self.max_step_half_length + STEP_LABEL_LENGTH

    def register_limit(self, register_id: int) -> int:
        if register_id == self.canvas_id:
            return self.max_canvas_length
        if register_id == STEP_REGISTER:
            return self.step_register_limit
        if register_id == TARGET_REGISTER and self.max_target_length is not None:
            return self.max_target_length
        if register_id in WIDE_REGISTERS:
            return self.max_special_length
        return self.max_register_length

    def summary_target(self, limit: int) -> int:
        """The budget the summariser is given, kept under the real limit.

        A budget at or above the limit leaves no headroom — every overshoot
        would then be a retry — so a configuration that asks for one is pulled
        back to three quarters of the register.
        """
        if self.summary_target_chars < limit:
            return self.summary_target_chars
        return max(1, limit * 3 // 4)

    def is_special(self, register_id: int) -> bool:
        return register_id < self.num_special_registers


    def register_name(self, register_id: int) -> str | None:
        if register_id == self.canvas_id:
            return "canvas"
        return REGISTER_NAMES.get(register_id)

    def __post_init__(self) -> None:
        if self.num_registers <= self.num_special_registers:
            raise ValueError("num_registers must exceed num_special_registers")
        if self.num_special_registers <= max(REGISTER_NAMES):
            named = ", ".join(f"{i} ({n})" for i, n in sorted(REGISTER_NAMES.items()))
            raise ValueError(f"registers {named} are system-written and must be special")
        if self.max_special_length > self.max_canvas_length:
            raise ValueError("the wide registers must stay smaller than the canvas")
        if self.max_special_length < self.max_register_length:
            raise ValueError("the wide registers must not be smaller than a normal one")
        if self.max_step_half_length < 1:
            raise ValueError("max_step_half_length must be at least 1")
        if self.max_target_length is not None:
            if self.max_target_length < self.max_register_length:
                raise ValueError("the target must not be smaller than a normal register")
            if self.max_target_length > self.max_canvas_length:
                raise ValueError("the target must stay smaller than the canvas")
        if self.step_register_limit > self.max_canvas_length:
            raise ValueError(
                f"register {STEP_REGISTER} holds both halves at once "
                f"({self.step_register_limit} chars) and must stay smaller than the canvas"
            )
        if self.max_steps is not None and self.max_steps < 1:
            raise ValueError("max_steps must be at least 1, or None for no cap")
        if self.summary_max_attempts < 1:
            raise ValueError("summary_max_attempts must be at least 1")
        if self.summary_target_chars < 1:
            raise ValueError("summary_target_chars must be at least 1")
        if self.summary_max_tokens < 1:
            raise ValueError("summary_max_tokens must be at least 1")
        if self.step_retry_seconds < 0:
            raise ValueError("step_retry_seconds must not be negative")
        if self.step_retry_backoff < 0:
            raise ValueError("step_retry_backoff must not be negative")
        if self.step_retry_backoff_max < self.step_retry_backoff:
            raise ValueError("step_retry_backoff_max must not be below the first backoff")
        if self.api_max_retries < 0:
            raise ValueError("api_max_retries must not be negative")
        if self.spawn_workers < 1:
            raise ValueError("spawn_workers must be at least 1")
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must not be negative, or None for no ceiling")
        if self.lookup_max_matches < 1:
            raise ValueError("lookup_max_matches must be at least 1")
        if self.check_timeout <= 0:
            raise ValueError("check_timeout must be positive")
        if self.max_context_tokens is not None:
            if self.max_context_tokens < 1:
                raise ValueError("max_context_tokens must be at least 1, or None")
            # The registers and the output cap can be checked here; the system
            # message and tool schemas are not known until an agent exists, so
            # the whole sum is checked again there against the real text.
            floor = int(self.dump_chars / CHARS_PER_TOKEN) + self.workspace_tokens
            if floor > self.max_context_tokens:
                raise ValueError(
                    f"one generation is at least {floor} tokens — {self.dump_chars} chars "
                    f"of registers and {self.workspace_tokens} of output — over the "
                    f"max_context_tokens of {self.max_context_tokens}"
                )


#: 0.0.7g: the same scaffold with one whole generation under 8,000 tokens.
#: Nothing about the mechanism changes — five tools, five special registers, the
#: summariser alongside the next step, concurrent bounded children — only how
#: much room each part is given, and how densely the scaffold states its own
#: rules. 0.0.7f-short reached 10,000 by shrinking the registers alone; 0.0.7g
#: reaches 8,000 because the fixed half of every request (system message and
#: tool schemas) came down from 4,479 tokens to 3,361 with every rule intact.
SHORT = dict(
    # 11 registers: 0-4 special, 5-9 the agent's, 10 the canvas. Five landing
    # registers is one per call for a five-call step, which is twice what any
    # run in the series has averaged.
    num_registers=11,
    max_register_length=208,
    #: Register 4, the summary — the run's whole memory of itself. The first
    #: short run set this at 768 against a 600-char budget and the summariser
    #: went over on all sixteen attempts it made in two minutes (812-1082
    #: chars), then at 1280 it still retried one step in eight (up to 1492).
    #: That is 0.0.6's lesson at small scale: the budget in the prompt does not
    #: set the length, the material does, and the register holds the overshoot.
    max_special_length=1536,
    #: Register 2, the target — written by the agent, which can be brief on
    #: purpose. Splitting it from the summary is worth 768 characters here,
    #: which is most of a canvas page.
    max_target_length=704,
    max_step_half_length=240,
    #: The reader: about thirty-eight lines of source a call.
    max_canvas_length=1536,
    #: One step writes about thirty-five lines of code, thinking paid out of the
    #: same budget. At this cap 16% of 0.0.7f-short's generations would have hit
    #: it against 11% at 2560 — the median step generates 777 tokens, and it is
    #: the file-writing steps that are cut and continued.
    workspace_tokens=1920,
    #: Under register 4, with the headroom that makes the overshoot free.
    summary_target_chars=600,
    summary_max_tokens=640,
    #: 8,000 at 0.0.7g. 0.0.8's prose is what moved it: the frame discipline,
    #: the optional destination, `lookup`, `resume`, and the registers-as-files
    #: sentence come to about 1,200 tokens of fixed constant that 0.0.7g did not
    #: pay. The register geometry is unchanged to the character, so this preset
    #: is still 0.0.7g's *input*; what it is not any more is 0.0.7g's price.
    max_context_tokens=9000,
)


#: 0.0.8: the frame scaffold. Same input geometry as 0.0.7i to the character
#: except the canvas, which 0.0.8a §5 argues is the one register a working set
#: has to land in whole — 1,536 chars holds twenty-five signature lines and the
#: distance to close was a factor of about 1.5, not of 16. What changes around
#: it is not size: `spawn` takes a brief a lossy caller can write, the check is
#: run at the pop, a child's steps come out of its parent's budget, the depth
#: ceiling is gone, `register_id` is optional, and the registers are files the
#: shell can reach.
FRAME = dict(
    num_registers=11,
    max_register_length=208,
    max_special_length=1536,
    max_target_length=704,
    max_step_half_length=240,
    #: 0.0.8a §5: nearer 4,096 than 1,536, so one working set fits in one place.
    max_canvas_length=4096,
    workspace_tokens=8192,
    summary_target_chars=600,
    summary_max_tokens=640,
    max_context_tokens=18000,
)


#: The same small active context, with the output cap taken off it. 0.0.7g's
#: ceiling covers input and output together, which is what an 8,000-token model
#: would impose; measured against the reconstruct task that turned out to bind
#: the wrong quantity. Reading is bounded by paging, and 8k reads a 39MB corpus
#: as well as 46k does. Writing is bounded by the output cap almost exactly:
#: 1,920 tokens a step produced 1.3 lines of code a step against 0.0.7f's 9.5 at
#: 16,384, and 5,500 lines is ~70,000 output tokens however it is sliced. Long
#: inputs are what degrade attention; long outputs are not, so this holds the
#: input where it was and gives the generation room.
WIDE_OUTPUT = dict(SHORT, workspace_tokens=8192, max_context_tokens=16000)


def frame_config(**overrides) -> "Config":
    """0.0.8: the frame scaffold."""
    return Config(**{**FRAME, **overrides})


def short_config(**overrides) -> "Config":
    """0.0.7g, with anything the caller wants to change on top."""
    return Config(**{**SHORT, **overrides})


def wide_output_config(**overrides) -> "Config":
    """0.0.7g's input, with a generation long enough to write with."""
    return Config(**{**WIDE_OUTPUT, **overrides})
