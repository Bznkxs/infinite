# Related Works

*Prior art for InfiniteAgent along three questions: **who has tried to build
agents that run indefinitely, and how**; **who keeps the context small at every
step** so that the effective context is never filled; and **which benchmarks test
arbitrarily long-horizon work** in a form this scaffold can run. Compiled
2026-10-01. §1.7 was extended on 2026-10-02 to cover **the loop that ended
0.0.8d and 0.0.8e**: who has seen it, why a counted warning does not stop it,
and what does.*

Related: [Design Tests (Top Down)](docs/Design%20Tests%20(Top%20Down).md) is the
claim these works are compared against; [Depth, Volume and
Width](docs/Depth,%20Volume%20and%20Width.md) names the three cost axes used
below; [Standard Evaluations](docs/Standard%20Evaluations.md) is what the
benchmark section is meant to extend.

**How to read an entry.** Each one gives the mechanism, then a *vs IA* line on how
it relates to InfiniteAgent. The features it is compared on are:

- a **fixed-shape context**: system message, tool schemas and a bounded register
  dump, the same size at step 1 and step 1,000;
- **stateless steps**: no conversation history at all;
- **state on disk**: everything else reached through `bash` and paged `load`;
- **`spawn`**: recursion into the same scaffold, with a goal, a check and a return
  schema;
- the **machine check**, run after every step;
- the **stall measure** and the **ledger** (0.0.8d/e).

**Context shape**, where it matters:

- **constant**: the same size every step;
- **sawtooth**: grows to a threshold, is compacted, then grows again;
- **slower**: still grows, just more slowly.

Almost everything in the literature is sawtooth or slower. Only a handful are
constant, and those are the closest prior art.

**Verification.** Every arXiv ID and URL below was checked against the abstract
page or the authors' own post during compilation, including spot checks of all
the 2026 items. Venue claims we could only see second-hand are marked
*[venue unverified]*.

---

## Contents

1. [Agents that try to run indefinitely, and how](#1-agents-that-try-to-run-indefinitely-and-how)
2. [Keeping the context small at all times](#2-keeping-the-context-small-at-all-times)
3. [Benchmarks for arbitrarily long-horizon tasks](#3-benchmarks-for-arbitrarily-long-horizon-tasks)
4. [Synthesis: where InfiniteAgent sits](#4-synthesis-where-infiniteagent-sits)

---

## 1. Agents that try to run indefinitely, and how

There are six recurring strategies. Most systems combine two or three of them.

| strategy                         | idea                                                                                           | examples                                                                       |
| -------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Virtual memory**               | a bounded in-context tier, paged to and from external storage                                  | MemGPT/Letta, MemoryOS, Memex                                                  |
| **Recursion**                    | sub-tasks run in isolated contexts; only the return value flows up                             | THREAD, RLM, PENCIL, Context-Folding, RAH                                      |
| **Reset and carry**              | throw history away and carry a small state forward                                             | Delethink, MEM1, MemAgent, InftyThink (§2.2–2.3)                               |
| **Fresh session, state on disk** | restart the agent with an empty context; progress lives in files, git and tests                | Anthropic's long-running harness, the Ralph loop, Carlini's C compiler, Cursor |
| **Compounding artefacts**        | the horizon extends through what accumulates outside the model: skills, workflows, reflections | Voyager, Generative Agents, Reflexion, AWM                                     |
| **Trained compaction**           | the model learns to compress its own history near the limit                                    | GPT-5.1-Codex-Max, ReSum, SUPO (§2.3)                                          |

InfiniteAgent uses the first three at once and at the finest grain. Every tool
step is a reset. The registers are the bounded tier. `spawn` is the recursion.

### 1.1 Virtual memory: a bounded tier plus paging

- **MemGPT: Towards LLMs as Operating Systems.** Packer, Wooders, Lin, Fang,
  Patil, Stoica, Gonzalez. 2023. [arXiv:2310.08560](https://arxiv.org/abs/2310.08560)
  - **Mechanism:** "virtual context management", modelled on OS memory
    hierarchies. Main context holds the system instructions, a writable "working
    context" block and a FIFO message queue. Archival and recall storage sit
    outside the context and are paged in by function calls. Interrupts and
    "heartbeats" chain calls together, and overflow triggers eviction plus
    recursive summarisation. Shape: sawtooth.
  - **vs IA:** the clearest ancestor of "registers plus disk plus tools"; its
    working-context block is the registers. But MemGPT keeps a message queue, so
    its steps are not stateless. It has no recursion and no progress model.
- **Letta memory blocks and Sleep-time Compute: Beyond Inference Scaling at
  Test-time.** Lin, Snell, Wang, Packer, Wooders, Stoica, Gonzalez. 2025.
  [arXiv:2504.13171](https://arxiv.org/abs/2504.13171) ·
  [memory blocks](https://www.letta.com/blog/memory-blocks/) ·
  [sleep-time compute](https://www.letta.com/blog/sleep-time-compute/)
  - **Mechanism:** labelled, size-limited "core memory blocks" are compiled into
    every prompt and edited by the agent with tools. A second "sleep-time" agent
    rewrites memory asynchronously between tasks.
  - **vs IA:** the blocks are bounded registers, and the sleep-time agent is a
    cousin of register 4's cheap summariser running alongside the next
    generation. Letta still keeps message history.
- **Memory OS of AI Agent (MemoryOS).** Kang et al. 2025, EMNLP 2025.
  [arXiv:2506.06326](https://arxiv.org/abs/2506.06326)
  - **Mechanism:** short-, mid- and long-term tiers with FIFO and segmented-page
    promotion. Built for personalised chat (LoCoMo), not task horizon.
- **Memex(RL): Scaling Long-Horizon LLM Agents via Indexed Experience Memory.**
  Wang, Chen, Wang, Wei. 2026.
  [arXiv:2603.04257](https://arxiv.org/abs/2603.04257)
  - **Mechanism:** the working context holds short structured summaries plus
    *stable indices*. Full-fidelity interactions sit in an external store and are
    recovered by dereferencing an index. RL learns what to archive and when to
    fetch, under a context budget, and the paper includes a theory of bounded
    in-context computation.
  - **vs IA:** almost exactly register 0's result pointer plus paged `load`. The
    difference is that Memex is trained, whereas IA leaves indexing to the
    agent's own file naming.
- **Mem0** (Chhikara et al. 2025, [arXiv:2504.19413](https://arxiv.org/abs/2504.19413)),
  **Zep** (Rasmussen et al. 2025, [arXiv:2501.13956](https://arxiv.org/abs/2501.13956))
  and **A-MEM** (Xu et al. 2025, [arXiv:2502.12110](https://arxiv.org/abs/2502.12110))
  - **Mechanism:** retrieval memories for multi-session chat, built on fact
    extraction, a temporal knowledge graph and Zettelkasten notes respectively.
  - **vs IA:** none bounds the prompt or can count. A-MEM's "memory evolution",
    where new notes rewrite old ones, is the kind of lossy rewrite the ledger
    exists to correct.

### 1.2 Recursion: a call stack of contexts

- **Recursive Language Models (RLM).** Zhang, Kraska, Khattab. 2025.
  [arXiv:2512.24601](https://arxiv.org/abs/2512.24601) ·
  [blog](https://alexzhang13.github.io/blog/2025/rlm/) · NeurIPS 2026 per the
  authors *[venue unverified]*
  - **Mechanism:** the long prompt is a variable in a Python REPL, never shown to
    the model. The root model writes code to peek at, split and grep it, and calls
    sub-models on the pieces. It handles inputs of 10M+ tokens, two orders of
    magnitude beyond the window, and presents this as a way around context rot.
    Evaluated on Oolong and BrowseComp-Plus.
  - **vs IA:** the closest published system, and the "recursive language model"
    the Design Tests already mention. Three differences:
    - the root's own REPL transcript still grows;
    - recursion is mostly depth 1 and aimed at *reading*, with nothing for
      writing;
    - there is no goal/check/return contract and no progress measure.

    RLM is the natural external baseline (§3.9).
- **Recursive Models for Long-Horizon Reasoning.** Yang, Srebro, Li. 2026.
  [arXiv:2603.02112](https://arxiv.org/abs/2603.02112)
  - **Mechanism:** the model recursively calls itself on subtasks in isolated
    contexts. The authors prove that any computable problem decomposes so that the
    active context needed is *exponentially* smaller than with a single sequence,
    and that summarisation-based sequential methods cannot match it. Extended to
    agents; tested on SAT and Go.
  - **vs IA:** the strongest theoretical argument for `spawn` over a summary-only
    design, and for the "stack mode" Design Test.
- **PENCIL: Long Thoughts with Short Memory.** Yang, Srebro, McAllester, Li.
  ICML 2025. [arXiv:2503.14337](https://arxiv.org/abs/2503.14337)
  - **Mechanism:** a learned reduction rule (CALL … SEP … RETURN) erases finished
    intermediate thoughts during generation, like a function return popping a
    frame. The authors prove it simulates Turing machines with optimal time and
    space. A 25M-parameter model with a 2,048-token context solves Einstein's
    puzzle.
  - **vs IA:** the same principle, a child's trajectory replaced by its return
    value, done at token level inside one model rather than at agent level.
- **THREAD: Thinking Deeper with Recursive Spawning.** Schroeder, Morgan, Luo,
  Glass. NAACL 2025. [arXiv:2405.17402](https://arxiv.org/abs/2405.17402)
  - **Mechanism:** generation is a thread that can spawn child threads. Children
    return only the tokens the parent needs.
  - **vs IA:** direct prior art for `spawn`. Each thread's own context still
    grows (shape: slower), and there is no per-step check.
- **Beyond Context Limits: Subconscious Threads for Long-Horizon Reasoning
  (TIM / TIMRUN).** Luo, Morgan, …, Schroeder, Glass. 2025.
  [arXiv:2507.16784](https://arxiv.org/abs/2507.16784)
  - **Mechanism:** reasoning is a tree of tasks, thoughts, subtasks and
    conclusions. The runtime prunes the KV cache of finished subtasks, giving
    "virtually unlimited" working memory inside one inference.
  - **vs IA:** a call stack enforced in the serving engine; it needs a trained
    model and a custom runtime.
- **Recursion of Thought: A Divide-and-Conquer Approach to Multi-Context
  Reasoning.** Lee, Kim. Findings of ACL 2023.
  [arXiv:2306.06891](https://arxiv.org/abs/2306.06891)
  - **Mechanism:** special tokens open a sub-problem in a fresh context and paste
    its answer back. An early "stack of contexts", trained on arithmetic.
- **ADaPT: As-Needed Decomposition and Planning with Language Models.** Prasad
  et al. Findings of NAACL 2024. [arXiv:2311.05772](https://arxiv.org/abs/2311.05772)
  - **Mechanism:** try to execute; on failure, recursively decompose. Depth
    adapts to difficulty.
  - **vs IA:** "descend only when needed", the second sentence of 0.0.8b's
    invariant. ADaPT's success signal is self-reported; IA's is a machine check.
- **ReDel: A Toolkit for LLM-Powered Recursive Multi-Agent Systems.** Zhu,
  Dugan, Callison-Burch. EMNLP 2024 Demo.
  [arXiv:2408.02248](https://arxiv.org/abs/2408.02248)
  - **Mechanism:** agents decide when and how to delegate, with logging and
    replay. Infrastructure, with no context bound and no check.
- **Recursive Agent Harnesses (RAH).** Lumer, Sen, Paul, Subbiah. 2026.
  [arXiv:2606.13643](https://arxiv.org/abs/2606.13643)
  - **Mechanism:** extends RLM so the recursive unit is a *full harness* with a
    filesystem and code execution. Parents write scripts that spawn parallel
    sub-harnesses. Oolong-Synthetic rises from 71.75% to 81.36%, at up to 4M
    tokens.
  - **vs IA:** the closest recent match to "children are the same scaffold". The
    abstract does not say whether each harness's context is bounded.
- **Scaling Long-Horizon LLM Agent via Context-Folding (FoldGRPO).** Sun, Lu et
  al. 2025. [arXiv:2510.11967](https://arxiv.org/abs/2510.11967) · ICML 2026
  per the authors *[venue unverified]*
  - **Mechanism:** `branch` into a sub-trajectory, then `return` folds it into a
    short summary. Trained with RL plus process rewards. Matches ReAct on deep
    research and SWE tasks with a 10× smaller active context.
  - **vs IA:** branch/return is `spawn`/response. The main thread still grows
    (shape: slower). They report that folding **beats rolling summarisation**,
    which bears on how much IA should lean on register 4.
- **AgentFold: Long-Horizon Web Agents with Proactive Context Management.** Ye
  et al. (Alibaba Tongyi). 2025. [arXiv:2510.24699](https://arxiv.org/abs/2510.24699)
  - **Mechanism:** at each step the policy chooses either a fine-grained
    condensation or a deep consolidation of whole sub-tasks into a typed record.
    SFT only; 36.2% on BrowseComp.
  - **vs IA:** it explicitly argues that "summarise the full history every step"
    loses detail irreversibly. That is the main published objection to register
    4's design (§4.3).
- **Recursive Introspection (RISE).** Qu et al. 2024.
  [arXiv:2407.18219](https://arxiv.org/abs/2407.18219)
  - **Not call-stack recursion**, despite the name: it is iterative
    self-correction. Cite it only to make the distinction.

### 1.3 Fresh sessions with state on disk: production long-running agents

These reach multi-day runs by restarting the agent with an empty context and
keeping progress in files, git and test suites. Within a session the context
still grows, so InfiniteAgent is this idea taken to its limit, with one tool step
per "session".

- **Effective harnesses for long-running agents.** Anthropic, 2025-11-26.
  [link](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
  - **Mechanism:** an *initializer* agent writes `init.sh`, a JSON feature list
    of 200+ items with pass/fail flags, `claude-progress.txt` and a first commit.
    Each later session starts fresh, reads the progress file and git log, does one
    feature, tests it end to end, then commits and updates the notes.
  - It targets two named failure modes: one-shotting the whole project, and
    declaring victory early.
  - **vs IA:** the same philosophy at session grain. The feature list with
    pass/fail flags is a hand-written analogue of IA's per-step check.
- **Building a C compiler with a team of parallel Claudes.** Carlini
  (Anthropic), 2026-02-05. [link](https://www.anthropic.com/engineering/building-c-compiler)
  - **Mechanism:** an infinite bash loop restarts Claude after each task, with 16
    instances in parallel. Coordination is through READMEs, progress files, task
    locks in `current_tasks/`, git, and test suites as the oracle (GCC as
    reference).
  - Produced about 100K lines of Rust that compiles Linux 6.9.
  - **vs IA:** a human still had to step in when every agent stalled on the same
    bug, which is the job IA's stall measure exists to do mechanically.
- **Ralph Wiggum as a "software engineer" (the Ralph loop).** Huntley,
  2025-07-14. [link](https://ghuntley.com/ralph/)
  - **Mechanism:** `while :; do cat PROMPT.md | claude-code ; done`. Each
    iteration starts empty and does one thing; state lives only in specs,
    `fix_plan.md`, `AGENT.md` and the code.
  - **vs IA:** folklore form of the stateless-step design.
- **Scaling long-running autonomous coding.** Cursor, January 2026.
  [link](https://cursor.com/blog/scaling-agents)
  - **Mechanism:** recursive planners spawn sub-planners; hundreds of workers
    execute; a judge closes each cycle, and the next cycle starts fresh.
  - Ran for about a week and built a browser of more than 1M lines. The authors
    write: "we still need periodic fresh starts to combat drift and tunnel
    vision."
- **Building more with GPT-5.1-Codex-Max.** OpenAI, 2025-11-18.
  [link](https://openai.com/index/gpt-5-1-codex-max/)
  - **Mechanism:** the first model *natively trained* to work across context
    windows by compaction. Reported internal runs exceed 24 hours.
  - **vs IA:** compaction moved into the weights; still sawtooth.
- **Claude Code compaction and subagents.**
  [subagents](https://code.claude.com/docs/en/sub-agents) ·
  [context window](https://code.claude.com/docs/en/context-window)
  - **Mechanism:** auto-compact replaces the conversation with a structured
    summary, then re-injects CLAUDE.md, memory and recent files from disk.
    Subagents start in isolated contexts and return summaries.
  - **vs IA:** one level of delegation, not a uniform recursion.
- **How we built our multi-agent research system.** Anthropic, June 2025.
  [link](https://www.anthropic.com/engineering/multi-agent-research-system)
  - **Mechanism:** the lead agent saves its plan to memory near the limit.
    Subagents write outputs to storage and pass back *lightweight references*,
    which is register 0's pointer convention.
- **Cognition: Don't Build Multi-Agents** ([link](https://cognition.ai/blog/dont-build-multi-agents))
  and **Rebuilding Devin for Claude Sonnet 4.5** ([link](https://cognition.com/blog/devin-sonnet-4-5-lessons-and-challenges))
  - **Mechanism:** the first argues for one writer per thread with shared traces,
    because "actions carry implicit decisions". The second reports "context
    anxiety": the model notices its window filling and summarises early.
  - **vs IA:** the first is the standing objection to `spawn`, and 0.0.8d's
    *seams* failure is an instance of it (§4.3). The second is a failure a
    fixed-size context cannot have.
- **SWE-agent: Agent-Computer Interfaces Enable Automated Software
  Engineering.** Yang, Jimenez et al. NeurIPS 2024.
  [arXiv:2405.15793](https://arxiv.org/abs/2405.15793)
  - **Mechanism:** a 100-line file viewer, capped search results, observations
    older than the last five collapsed to one line, and tracked state variables.
  - **vs IA:** the origin of bounded tool output plus paged `load`.
- **OpenHands context condenser.**
  [blog](https://www.openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents) ·
  [docs](https://docs.openhands.dev/sdk/guides/context-condenser)
  - **Mechanism:** keep the first N and last M events and summarise the middle
    past a threshold. About 2× lower per-turn cost at equal SWE-bench accuracy.
    Shape: sawtooth.

### 1.4 Lifelong and open-ended agents

These extend the horizon through artefacts that accumulate outside the model,
not through context management.

- **Voyager.** Wang et al. 2023. [arXiv:2305.16291](https://arxiv.org/abs/2305.16291)
  - **Mechanism:** an automatic curriculum, a growing skill library of executable
    code, and self-verification against the environment, for lifelong Minecraft
    play.
  - **vs IA:** self-verification is a precursor of the machine check.
- **Generative Agents: Interactive Simulacra of Human Behavior.** Park et al.
  UIST 2023. [arXiv:2304.03442](https://arxiv.org/abs/2304.03442)
  - **Mechanism:** a memory stream retrieved by recency, importance and
    relevance; periodic *reflection*; recursive day-to-action planning.
  - **vs IA:** reflection is a lossy summary. The stream grows without bound;
    only retrieval is bounded.
- **Reflexion.** Shinn et al. NeurIPS 2023.
  [arXiv:2303.11366](https://arxiv.org/abs/2303.11366)
  - **Mechanism:** verbal reflections carried across trials. Cross-episode, not
    within-task.
- **JARVIS-1** (Wang et al. 2023, [arXiv:2311.05997](https://arxiv.org/abs/2311.05997))
  and **Agent Workflow Memory** (Wang, Mao, Fried, Neubig 2024,
  [arXiv:2409.07429](https://arxiv.org/abs/2409.07429))
  - **Mechanism:** retrieved plans, and induced reusable workflows (+51% relative
    on WebArena).
- **Agentic Context Engineering (ACE).** Zhang et al. ICLR 2026.
  [arXiv:2510.04618](https://arxiv.org/abs/2510.04618)
  - **Mechanism:** a generator, reflector and curator maintain an evolving
    "playbook" through *incremental* updates, because wholesale rewriting causes
    **context collapse** and brevity bias.
  - **vs IA:** register 4 is rewritten whole every step by a small model, which
    is exactly the regime ACE warns about. The ledger, and the summariser being
    forbidden to assert outcomes, are IA's answer (§4.3).
- **Cognitive Architectures for Language Agents (CoALA).** Sumers, Yao,
  Narasimhan, Griffiths. TMLR 2024.
  [arXiv:2309.02427](https://arxiv.org/abs/2309.02427)
  - **Mechanism:** a framework: working versus long-term (episodic, semantic,
    procedural) memory, and internal versus external actions.
  - **vs IA:** the registers are CoALA working memory with a hard size limit,
    disk is long-term memory, and `set` is an internal action.

### 1.5 Agents actually run for very long

- **Vending-Bench: A Benchmark for Long-Term Coherence of Autonomous Agents.**
  Backlund, Petersson (Andon Labs). 2025.
  [arXiv:2502.15840](https://arxiv.org/abs/2502.15840)
  - **Mechanism:** the scaffold keeps the last 30K tokens plus a scratchpad, a
    key-value store and a vector DB; runs exceed 20M tokens.
  - **Key finding: breakdowns do not correlate with the point where the context
    fills.** Agents misread schedules, forget orders and enter "meltdown loops".
  - **vs IA:** bounding the context is necessary but not sufficient. This is the
    published case for the check, the stall measure and the ledger.
- **Project Vend.** Anthropic and Andon Labs.
  [phase 1](https://www.anthropic.com/research/project-vend-1) (2025-06-27) ·
  [phase 2](https://www.anthropic.com/research/project-vend-2) (2025-12-18)
  - **Mechanism:** Claude ran a real shop for weeks on note-keeping tools,
    because "the full history … would overwhelm the context window". It failed to
    learn from repeated mistakes.
  - Phase 2 added a CRM, a supervising agent and mandatory verification, and
    became profitable.
  - **vs IA:** structured external state and a supervisor fixed what free-form
    notes could not, much as the ledger and the target register do.
- **AI Village** (AI Digest / Sage), running since April 2025.
  [how it works](https://aivillageblog.substack.com/p/how-the-ai-village-works) ·
  [2025 retrospective](https://theaidigest.org/village/blog/what-we-learned-2025)
  - **Mechanism:** every 40 actions, agents must "consolidate" notes into memory
    and are told to shorten it when it grows long. Agents still forget key facts:
    the lossy-summary problem at scale.

### 1.6 Computational universality: the theory behind the Turing-completeness test

- **Memory Augmented Large Language Models are Computationally Universal.**
  Schuurmans. 2023. [arXiv:2301.04589](https://arxiv.org/abs/2301.04589)
  - **Mechanism:** a bounded-context LM on its own is a finite automaton. Add an
    associative read/write memory and a fixed prompt loop, and Flan-U-PaLM 540B
    simulates the universal Turing machine U(15,2) with no weight changes.
  - **vs IA:** the formal template for the Computational Completeness clause:
    stateless bounded-context calls plus external read/write memory plus a loop.
    The registers and disk are that memory.
- **Autoregressive Large Language Models are Computationally Universal.**
  Schuurmans, Dai, Zanini. 2024. [arXiv:2410.03170](https://arxiv.org/abs/2410.03170)
  - **Mechanism:** a system prompt makes Gemini-1.5-pro apply 2,027 Lag-system
    rules. Universal, but it relies on an unbounded sliding window.
  - A template for a probe whose rules live on disk (§3.5).
- **Position: The Turing-Completeness of Autoregressive Transformers Relies
  Heavily on Context Management.** Cui, Wei, He. 2026.
  [arXiv:2605.19514](https://arxiv.org/abs/2605.19514)
  - **Mechanism:** argues that context management is "a central component that
    critically determines the computational power" of a deployed system. A fixed
    system and a family of models scaled with input length are different claims.
  - **vs IA:** the clause, stated as a position, and the citation for why a fixed
    context must be paired with an external store.
- **On the Turing Completeness of Transformers and Agents.** Qiao, Yu, Qiu, Gao.
  2026. [arXiv:2609.20335](https://arxiv.org/abs/2609.20335)
  - **Mechanism:** a single fixed finite-precision transformer is not Turing
    complete; agents with decision, execution and memory modules are.
- **The Expressive Power of Low Precision Softmax Transformers with (Summarized)
  Chain-of-Thought.** Brösamle, Eckstein. ICML 2026.
  [arXiv:2605.18079](https://arxiv.org/abs/2605.18079)
  - **Mechanism:** with *summarised* chain of thought, model size scales with the
    space bound rather than the time bound. Theoretical support for "constant
    context, unbounded steps".
- **Ask, and it shall be given: On the Turing completeness of prompting.** Qiu
  et al. ICLR 2025. [arXiv:2411.01992](https://arxiv.org/abs/2411.01992)
- **The Expressive Power of Transformers with Chain of Thought.** Merrill,
  Sabharwal. ICLR 2024. [link](https://iclr.cc/virtual/2024/poster/18776)
  - Power grows with chain-of-thought length.
- **Ancestors:**
  - **Neural Turing Machines** (Graves, Wayne, Danihelka 2014,
    [arXiv:1410.5401](https://arxiv.org/abs/1410.5401)) and the
    **Differentiable Neural Computer** (Graves et al., *Nature* 538, 2016,
    [link](https://www.nature.com/articles/nature20101)): a controller with
    bounded heads over a large tape.
  - **Scratchpads** (Nye et al. 2021, [arXiv:2112.00114](https://arxiv.org/abs/2112.00114))
    and **Self-Notes** (Lanchantin et al. NeurIPS 2023,
    [arXiv:2305.00833](https://arxiv.org/abs/2305.00833)): written intermediate
    state, but inside a growing context.

### 1.7 Loops, stalls and livelock

This is the failure that ended 0.0.8d and 0.0.8e, so the subsection starts with
what it is. The evidence is in [Lossy Memory and the
Loop](docs/Lossy%20Memory%20and%20the%20Loop.md) and [0.0.8e
§4.2](docs/InfiniteAgent%200.0.8e.md):

- **It is a read-only livelock, not repetition.** A frame reads and re-runs
  diagnostics and never writes. In 0.0.8d, 103 of the root's 120 steps changed
  nothing durable. In 0.0.8e one frame stalled on 58 of 74 steps, reading
  `smoke.py` 16 times and `shell.py` 7 times without editing either. 99% of the
  looping frame's commands were distinct, which a repetition detector would miss.
- **The run's memory sustained it.** Register 4 said the bug was fixed four
  separate times. It was never fixed.
- **Telling the frame did not stop it.** The `[Stall]` line was read past for 31
  steps, and the counted `[Ledger]` line for 38 of 74. The only thing that has
  ever changed this agent's behaviour is removing a tool. So the next candidate is
  refusing read-only steps at a stall threshold (0.0.8d §10.3).

The works below are grouped by those three facts, then by what to do instead.
Most prior work detects *repeated surface behaviour*; IA asks whether *durable
state changed*. This subsection was extended on 2026-10-02. Each paper's abstract
page was opened, and production thresholds were read from the source files
linked. Classical items that could only be checked at citation level are marked
*[citation-level]*.

#### 1.7.1 The same failure, measured elsewhere

- **The Danger of Overthinking: Examining the Reasoning-Action Dilemma in Agentic
  Tasks.** Cuadron et al. 2025.
  [arXiv:2502.08235](https://arxiv.org/abs/2502.08235)
  - **Mechanism:** 4,018 SWE-bench Verified trajectories. It names three
    patterns: *Analysis Paralysis*, *Rogue Actions* and *Premature
    Disengagement*. A higher overthinking score goes with a lower resolve rate.
    Picking the least-overthinking of 2–3 samples gains almost 30% and cuts cost
    by 43%. Native function calling cut the score from 2.43 to 1.05 and raised
    resolution from 29.1% to 47.7%.
  - **vs IA:** the closest named precedent. Their paralysis is reasoning in place
    of acting. IA's frame does act, but its actions never change state. That the
    *interface* moved the behaviour, where prompting did not, is the point for
    §1.7.5.
- **Failure as a Process: An Anatomy of CLI Coding Agent Trajectories.** Zhao, …,
  Barr, Sarro, Ye. 2026. [arXiv:2607.09510](https://arxiv.org/abs/2607.09510)
  - **Mechanism:** 1,794 annotated Terminal-Bench trajectories, 7 models, 3
    scaffolds, more than 63K steps. Failures are mostly epistemic and begin early;
    the median onset of the decisive error is step 7. From the paper body:
    - "keeps repeating the same approach": 15% of failures, 29% of wasted steps;
    - "repairs the wrong problem": 24% of failures, 39% of waste;
    - "performs checks that cannot change the outcome": 28% of failed runs.
  - **vs IA:** the third class is close to a description of the 0.0.8e frame.
    The paper calls for earlier intervention rather than outcome grading.
- **Understanding Software Engineering Agents: A Study of Thought-Action-Result
  Trajectories.** Bouzenia, Pradel. ASE 2025.
  [arXiv:2506.18824](https://arxiv.org/abs/2506.18824)
  - **Mechanism:** 120 trajectories from RepairAgent, AutoCodeRover and
    OpenHands. Failed runs are longer (RepairAgent: 40 iterations against 22). The
    anti-patterns it names include searches whose results are never acted on,
    fixes that are never tested, and "repetitive, non-adaptive cycles".
  - **vs IA:** "searches whose results are never acted on" is read-without-edit.
- **Understanding Code Agent Behaviour: An Empirical Study of Success and Failure
  Trajectories.** Majgaonkar, …, Sarro, Ye. 2025.
  [arXiv:2511.00197](https://arxiv.org/abs/2511.00197)
  - **Mechanism:** OpenHands, SWE-agent and Prometheus on SWE-bench. In 72–81% of
    failures the agent still localised the right file.
  - **vs IA:** failure is in carrying the fix out, not in diagnosis. That matches
    a frame that read `smoke.py` sixteen times and knew where the bug was.
- **Beyond Resolution Rates: Behavioral Drivers of Coding Agent Success and
  Failure.** Mehtiyev, Assunção. 2026.
  [arXiv:2604.02547](https://arxiv.org/abs/2604.02547)
  - **Mechanism:** 9,374 trajectories from 19 agents. Successful agents gather
    context before editing. Once difficulty is controlled for, the usual link
    between trajectory length and failure reverses.
  - **vs IA:** the caution. A long reading phase is not itself the defect, so any
    threshold should key on durable state change, not on step count.
- **The Debugging Decay Index: Rethinking Debugging Strategies for Code LLMs.**
  Adnan, Kuhn. *Scientific Reports* 15, 2025.
  [arXiv:2506.18403](https://arxiv.org/abs/2506.18403)
  - **Mechanism:** across 18 models, debugging effectiveness decays
    exponentially; most lose 60–80% of it within 2–3 attempts. A "strategic fresh
    start" at the predicted decay point restores it.
  - **vs IA:** a number for how quickly a frame stuck on one bug stops being worth
    continuing.
- **Is Self-Repair a Silver Bullet for Code Generation?** Olausson et al. ICLR
  2024. [arXiv:2306.09896](https://arxiv.org/abs/2306.09896)
  - **Mechanism:** once its cost is counted, self-repair's gain is often modest.
    The bottleneck is the model's feedback on its own code, and feedback from a
    stronger model or a human raises the gain substantially.
  - **vs IA:** a frame looping on its own diagnosis has exactly that bottleneck.
    The fix is a signal from outside the frame: the check, a parent or a child.
- **Why Do Multi-Agent LLM Systems Fail? (MAST).** Cemri, Pan, Yang et al. 2025.
  [arXiv:2503.13657](https://arxiv.org/abs/2503.13657)
  - **Mechanism:** a taxonomy of 14 failure modes, in which "step repetition"
    (FM-1.3) is among the most common.

#### 1.7.2 Detectors, and what each one can see

Production coding agents, read from source:

| system | what it matches | threshold | then |
| --- | --- | --- | --- |
| **OpenHands** Stuck Detector ([docs](https://docs.openhands.dev/sdk/guides/agent-stuck-detector)) | the same action and observation; the same action and error; monologue; A/B alternation; context-window errors | 4; 3; 3 messages; 6 cycles; repeated | stop |
| **Gemini CLI** `LoopDetectionService` ([source](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/loopDetectionService.ts)) | (1) SHA-256 of tool name plus arguments, cycles of length 1–5; (2) repeated 50-character content chunks; (3) an **LLM judge** over the last 20 turns | (1) 5 repeats; (2) 10; (3) from turn 30, re-run every 5–15 turns, fires at confidence ≥ 0.9 once a second model agrees | first detection injects *"Potential loop detected … take a step back"*; the second halts |
| **Cline** ([repo](https://github.com/cline/cline), `sdk/packages/core/src/runtime/safety/loop-detection.ts`, `mistake-tracker.ts`) | consecutive identical calls (name plus key-sorted args); separately, consecutive errors | 3 soft, 5 hard; errors 6 (SDK) or 3 (CLI) | soft: "consider trying a different approach"; hard: stop; errors: ask the user |
| **Roo Code** ([repo](https://github.com/RooCodeInc/Roo-Code), `src/core/tools/ToolRepetitionDetector.ts`) | the same call as the previous one; turns with no tool call | `consecutiveMistakeLimit`, default 3 | **refuses the repeated call** (`allowExecution: false`) and asks the user |
| **goose** ([repo](https://github.com/block/goose), `crates/goose/src/tool_monitor.rs`) | the same tool with identical parameters | `--max-tool-repetitions N`, off by default | denies the call |
| **Aider** (`aider/coders/base_coder.py`) and **SWE-agent** ([docs](https://swe-agent.com/latest/reference/agent/)) | nothing: budgets only | Aider: 3 lint/test reflections; SWE-agent: a per-instance cost limit | Aider stops; SWE-agent **autosubmits** the current diff, and `RetryAgent` runs fresh attempts |

**What the table says about IA's loop:**

- Every detector here except Gemini CLI's judge matches a hash of the tool call.
  With 99% distinct commands, IA's loop passes all of them.
- Gemini's judge is the only one that asks IA's question. Its prompt requires
  both a repetitive pattern and "NO net change or forward progress", and it
  exempts incremental edits and retries with variation. But its first response is
  a textual warning, the kind IA has found ineffective.
- Roo Code and goose come closest to withdrawal. They refuse the call, but only
  the exact repeated one.
- No production agent found withdraws a *class* of tool on a stall.
- OpenHands has known false positives on long-running commands. That mirrors
  IA's own 0.0.8e defect, where a red check counted as progress.
- Codex CLI and Claude Code have no loop detector in their public sources or docs.

Research detectors and supervisors:

- **Unsupervised Cycle Detection in Agentic Applications.** George et al. (IBM).
  2025. [arXiv:2511.10650](https://arxiv.org/abs/2511.10650)
  - **Mechanism:** call-stack analysis plus semantic similarity. F1 is 0.72,
    against 0.08 for structure alone.
- **Real-Time Detection and Repair of LLM Agent Failures.** Dubey. 2026.
  [arXiv:2608.02464](https://arxiv.org/abs/2608.02464)
  - **Mechanism:** an echo-state-network ensemble with CUSUM alarms over step
    telemetry, plus a deterministic layer that **recomputes the totals the agent
    stated from the actual tool results**. Rollback and re-execution raise success
    from 52% to 73%.
  - **vs IA:** the deterministic recount is the ledger's principle: do not ask
    the model to count.
- **AgentLoop: Runtime Control of Slot-closed Execution Loops for
  Tool-augmented LLM Agents.** Zheng, Xu, Hu, Ye, Xu. 2026.
  [arXiv:2609.33315](https://arxiv.org/abs/2609.33315)
  - **Mechanism:** tracks whether the information "slots" a request needs are
    covered by runtime evidence, and stops on low gain.
  - **vs IA:** a progress-plus-completion controller, the analogue of the stall
    measure plus the check.
- **Stop Wasting Your Tokens: Towards Efficient Runtime Multi-Agent Systems
  (SupervisorAgent).** Lin et al. ICLR 2026.
  [arXiv:2510.26585](https://arxiv.org/abs/2510.26585)
  - **Mechanism:** an LLM-free filter wakes a supervisor on errors, on repetition
    (identical action and observation, or too many steps) and on observations
    over 3,000 characters. The supervisor chooses *approve*, *provide_guidance*,
    *correct_observation* or *run_verification*. Smolagent on GAIA uses 29.68%
    fewer tokens at unchanged success.
  - **vs IA:** a surface trigger, but a useful action set. It separates
    *guidance*, which is a warning, from *correcting what the agent sees*, which
    is not.
- **AgentTether: Graph-Guided Diagnosis and Runtime Intervention.** Zhao et al.
  2026. [arXiv:2607.06273](https://arxiv.org/abs/2607.06273)
  - **Mechanism:** detects drift, including loop repetition, against a model of
    normal behaviour, then re-executes with guidance from a "Repair Memory".
    Repairs 59–65% of failed tasks on τ-bench Banking.
- **Magentic-One's progress ledger**: see §1.7.5. It is a detector and an
  escalation in one.

#### 1.7.3 Why a counted warning is read past

The question 0.0.8e left is why a frame that is told, accurately and with
numbers, that it has read `smoke.py` sixteen times reads it a seventeenth time.

- **Feedback That Backfires: Why Small Language Model Agents Repeat the Call They
  Just Watched Fail.** Gumaan. 2026.
  [arXiv:2608.23651](https://arxiv.org/abs/2608.23651)
  - **Mechanism:** an error message in the transcript makes repeating the failed
    call *more* likely, in every instruction-tuned model tested. Among restricted
    candidates, the probability of repeating rises from 0.06 to 0.54. **The
    failed call's surface form accounts for 83% of the damage**; the label saying
    it failed contributes little. From the paper body: a "do not repeat"
    instruction did not help, deleting the failure made things worse, and
    replacing the verbatim call with a runtime-written description removed most
    of the effect.
  - **vs IA:** the closest mechanistic match to the ledger. `read since:
    smoke.py x16` puts in front of the model the exact string it is drawn to
    copy. So the ledger's *wording* may feed the loop it describes. Caveats: one
    author, models of 135M–1.7B only.
- **LLMs are Greedy Agents: Effects of RL Fine-tuning on Decision-Making
  Abilities.** Schmied et al. 2025.
  [arXiv:2504.16078](https://arxiv.org/abs/2504.16078)
  - **Mechanism:** names three failure modes: greediness, *frequency bias* and a
    *knowing-doing gap*. From the paper body: 87% of rationales were correct, yet
    the model still took the greedy action 58% of the time. Small models chose
    whichever action was most frequent in context. RL fine-tuning on the model's
    own reasoning narrows the gap.
  - **vs IA:** this is "the thinking says the right thing, the action repeats the
    frequent thing". Frequency bias predicts that a dump mentioning `smoke.py`
    pulls toward another read of `smoke.py`.
- **Learning to Break the Loop: Analyzing and Mitigating Repetitions for Neural
  Text Generation.** Xu et al. NeurIPS 2022.
  [arXiv:2206.02369](https://arxiv.org/abs/2206.02369)
  - **Mechanism:** repetition **reinforces itself**: the more times a sentence is
    already in context, the more likely it is generated again.
  - **vs IA:** the token-level ancestor of the action loop.
- **Wait, Wait, Wait… Why Do Reasoning Models Loop?** Pipis, Garg, Kontonis,
  Shrivastava, Krishnamurthy, Papailiopoulos. ICML 2026 (spotlight).
  [arXiv:2512.12895](https://arxiv.org/abs/2512.12895)
  - **Mechanism:** loops come from risk aversion: when the action that makes
    progress is hard to learn and an easy cyclic action is available, probability
    moves onto the cyclic one. Transformers also tend toward temporally correlated
    errors. Temperature is "a stopgap rather than a holistic solution".
  - **vs IA:** re-reading is the easy cyclic action and editing is the hard one.
    Taking the easy action off the menu targets this mechanism directly; a
    warning does not.
- **Feedback Friction: LLMs Struggle to Fully Incorporate External Feedback.**
  Jiang et al. 2025. [arXiv:2506.11930](https://arxiv.org/abs/2506.11930)
  - **Mechanism:** given near-perfect feedback over several retries, models
    still plateau below the achievable score. Confident answers resist correction
    most.
  - **vs IA:** a confident "it is fixed" is the belief hardest to dislodge, even
    with a red check in the dump.
- **LLMs cannot find reasoning errors, but can correct them given the error
  location.** Tyen et al. Findings of ACL 2024.
  [arXiv:2311.08516](https://arxiv.org/abs/2311.08516)
  - **Mechanism:** self-correction fails at *locating* the mistake, not at fixing
    it; given the location, models correct well.
  - **vs IA:** a notice should point at *where* (which assertion fails, which call
    site) rather than *how long*. "No progress for 12 steps" carries no location.
- **Large Language Models Cannot Self-Correct Reasoning Yet** (Huang et al., ICLR
  2024, [arXiv:2310.01798](https://arxiv.org/abs/2310.01798)) and **On the
  Self-Verification Limitations of LLMs on Reasoning and Planning Tasks** (Stechly,
  Valmeekam, Kambhampati 2024, [arXiv:2402.08115](https://arxiv.org/abs/2402.08115))
  - **Mechanism:** without external feedback, self-correction does not help and
    sometimes hurts. A sound external verifier helps substantially.
  - **vs IA:** "let me look one more time", with no check to look against, is not
    expected to converge.
- **Measuring and Controlling Instruction (In)Stability in Language Model
  Dialogs.** Li et al. COLM 2024.
  [arXiv:2402.10962](https://arxiv.org/abs/2402.10962)
  - **Mechanism:** adherence to the system prompt drifts within eight rounds,
    which the authors attribute to attention decay.
  - **vs IA:** IA has no rounds, so this mechanism should not apply to a
    stateless step. That it was read past anyway suggests the defect is not decay.
- **Retrospective Progress-Aware Self-Refinement (RePro).** Ma et al. 2026.
  [arXiv:2606.14302](https://arxiv.org/abs/2606.14302)
  - **Mechanism:** prompting agents to assess their own progress *during* a run
    reduced performance. Assessing it retrospectively, after the outcome is
    known, helped, by up to 12 points on WebShop, ALFWorld and Sokoban.
  - **vs IA:** indirect evidence that putting progress in the context mid-run
    need not help.
- **Counter-evidence: Understanding the Weakness of Large Language Model Agents
  within a Complex Android Environment.** Xing et al. 2024.
  [arXiv:2402.06596](https://arxiv.org/abs/2402.06596)
  - **Mechanism:** a UCB-style hint at every step, *"You have already been in the
    current state M times, and taken action A for N times"*, raised GPT-4's
    success rate by 27% on the Camera app.
  - **vs IA:** a counted hint in the context *did* change behaviour there. The
    differences from the `[Ledger]` are the model, a short-horizon GUI task, and a
    hint about the action being chosen rather than a summary of the past. It is
    the one result that says the ledger's failure is not universal.
- **Can large language models explore in-context?** Krishnamurthy et al. NeurIPS
  2024. [arXiv:2403.15371](https://arxiv.org/abs/2403.15371)
  - **Mechanism:** in bandits, only GPT-4 with chain-of-thought *and an
    externally summarised interaction history* explored satisfactorily.
  - **vs IA:** what helped was a summary computed outside the model, which is the
    ledger's design rather than register 4's.

No paper found measures habituation to a repeated warning in an LLM. The
habituation literature is about people. *Feedback That Backfires* is the nearest
empirical substitute.

#### 1.7.4 A memory that says "fixed"

Register 4 recorded the agent's *belief* that the bug was fixed as a fact, four
times. 0.0.8e §2.3 now forbids the summary from claiming a machine verdict. These
works say why that is the right line to draw.

- **How Language Model Hallucinations Can Snowball.** Zhang, Press, Merrill, Liu,
  Smith. 2023. [arXiv:2305.13534](https://arxiv.org/abs/2305.13534)
  - **Mechanism:** models over-commit to early mistakes and justify them, even
    though, asked separately, they recognise 67% (ChatGPT) and 87% (GPT-4) of
    those claims as false.
  - **vs IA:** once "fixed" is in the summary, the pressure to stay consistent
    keeps it there.
- **When Do Agent Loops Mistake Stagnation for Progress? Self-Evaluation Bias and
  Externally Grounded Verification in Long-Running Autonomous LLM Agent Loops.**
  Park, Choi. 2026. [arXiv:2607.25152](https://arxiv.org/abs/2607.25152)
  - **Mechanism:** the "**progress mirage**". Over 54 cycles a frontier agent
    claimed improvement every time; 56% had zero or negative measured change.
    Evaluators accepted regressions 44% of the time and rejected real
    improvements 38% of the time. Out-of-band evaluation with real-world access
    is "a structural requirement".
  - **vs IA:** the closest published analogue of the 58-row table in Lossy
    Memory, and an argument that the check, not any model, owns the verdict.
- **From Confident Closing to Silent Failure: Characterizing False Success in LLM
  Agents.** Advani. FAGEN@ICML 2026.
  [arXiv:2606.09863](https://arxiv.org/abs/2606.09863)
  - **Mechanism:** about 12,000 trajectories. False success is 3% to 75.8% of
    outcomes by domain. LLM judges fail reliably (no configuration above AUROC
    0.65) because they reward confident language. Lightweight domain-calibrated
    detectors reach 0.95.
  - **vs IA:** a judge model reading the transcript would have believed "fixed"
    too. A machine signal is what catches it.
- **How Coding Agents Fail Their Users: A Large-Scale Analysis of
  Developer-Agent Misalignment in 20,574 Real-World Sessions.** Tang et al. 2026.
  [arXiv:2605.29442](https://arxiv.org/abs/2605.29442)
  - **Mechanism:** one of seven failure categories is inaccurate progress
    reporting: premature success claims and unverified states reported as done.
    Its share is *growing* even as overall misalignment falls.
- **The Hallucination Snowball: Modeling Error Propagation as State Transitions
  in Multi-Agent LLM Pipelines.** Singh, Pawar. FAGEN@ICML 2026.
  [arXiv:2608.14588](https://arxiv.org/abs/2608.14588)
  - **Mechanism:** an error moves from raw fact to derived computation to prose
    to conclusion. GPT-4o's detection falls from 72.0% at the first stage to 50.9%
    at the last. A gate at the first handoff cuts survival from 58.4% to 16.2%;
    "when you verify matters more than whether you verify".
  - **vs IA:** register 4 does that laundering in a single step, from "the agent
    thinks it fixed it" to "fixed". The gate belongs where the step record enters
    the summary.
- **Which Agent Causes Task Failures and When? (Who&When)** (Zhang et al. 2025,
  [arXiv:2505.00212](https://arxiv.org/abs/2505.00212)) and **TRAIL: Trace
  Reasoning and Agentic Issue Localization** (Deshpande et al. 2025,
  [arXiv:2505.08638](https://arxiv.org/abs/2505.08638))
  - **Mechanism:** LLMs locate failures in agent logs poorly: 14.2% at step level
    in Who&When, and 11% in TRAIL for the best model.
  - **vs IA:** a small model reading one step at a time is not positioned to know
    whether the bug is fixed.

#### 1.7.5 Remedies that change what the agent can do

**Remove the action rather than price it.** This is 0.0.8d §10.3's tier, and it
has the most support of anything here.

- **A Closer Look at Invalid Action Masking in Policy Gradient Algorithms.**
  Huang, Ontañón. FLAIRS-35, 2022.
  [arXiv:2006.14171](https://arxiv.org/abs/2006.14171)
  - **Mechanism:** in µRTS, masking invalid actions scales to every map size. An
    invalid-action *penalty* "fails to scale, sometimes struggling to find even
    the first reward". Agents trained with masking and evaluated without it
    degrade but still beat penalty-trained agents.
  - **vs IA:** the RL form of IA's own finding. The stall surcharge, a price,
    failed; removing `spawn` worked. The masking-removed result suggests a frame
    is not left helpless when its tools come back.
- **Manus: "mask, don't remove."**
  [link](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
  - **Mechanism:** do not delete tools mid-loop, for two reasons: tool
    definitions sit near the front of the context, so removing one breaks the KV
    cache; and earlier actions that name a now-missing tool confuse the model.
    Instead, a state machine masks token logits, and tool names share prefixes
    (`browser_`, `shell_`) so a whole group can be masked at once.
  - **vs IA:** the strongest argument against literally deleting `load` from the
    schema. The confusion argument is weak for IA, whose stateless steps keep no
    history naming the tool. The cache argument holds. A harness refusal or a
    group mask (all read-shaped tools) keeps the schema stable.
- **Anthropic API, `tool_choice`.**
  [docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
  - **Mechanism:** `auto`, `any`, `tool` and `none`. Forcing with `any` or `tool`
    returns a 400 on Claude Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1, and is
    unsupported under manual extended thinking. Changing `tool_choice` invalidates
    cached message blocks.
  - **vs IA:** IA's default, `claude-opus-5`, supports forcing, but the next model
    up does not. So schema-level removal or a harness refusal is the route that
    survives a model change.
- **StateFlow: Enhancing LLM Task-Solving through State-Driven Workflows.** Wu et
  al. 2024. [arXiv:2403.11322](https://arxiv.org/abs/2403.11322)
  - **Mechanism:** the task is a state machine, and each state has its own prompt
    and allowed tools. +13% over ReAct on InterCode SQL at a fifth of the cost,
    and +28% on ALFWorld at a third.
  - **vs IA:** the answer to "the scaffold imposing a shape". Gating tools by
    state *raised* success rather than costing it.
- **Enforcing Temporal Constraints for LLM Agents (Agent-C).** Kamath et al.
  2025. [arXiv:2512.23738](https://arxiv.org/abs/2512.23738)
  - **Mechanism:** ordering rules are compiled to logic and checked by an SMT
    solver *during* generation, and constrained decoding steers to a compliant
    call instead of rejecting. Conformance reaches 100% and utility rises for
    Claude Sonnet 4.5 (71.8% → 75.2%) and GPT-5 (66.1% → 70.6%).
  - **vs IA:** redirect, do not just refuse. The refusal should name what the
    frame *may* do: write, `spawn`, or respond.
- **Tabu Search, Part I.** Glover. *ORSA Journal on Computing* 1(3), 1989.
  - **Mechanism:** recently used move attributes become *tabu* for a tenure.
    *Aspiration criteria* lift the ban when a move beats a recorded level. A
    long-term frequency memory drives the search into unexplored territory.
    Glover notes that tabu lists built to forbid exact *repetition*, rather than
    a class of move, "typically do not work well".
  - **vs IA:** the classical form of "forbid the re-read until something moves".
    It argues for forbidding the *class* (read-only steps), not a list of exact
    repeats, which is what Roo Code and goose do. An aspiration criterion is
    IA's "the tools come back once something moves".
- **Cuadron et al.** (§1.7.1): moving to native function calling halved
  overthinking where prompting had not.

**Force the commit.**

- **s1: Simple test-time scaling.** Muennighoff et al. 2025.
  [arXiv:2501.19393](https://arxiv.org/abs/2501.19393)
  - **Mechanism:** "budget forcing": the decoder ends thinking when the budget
    runs out, or appends "Wait" to extend it. AIME24 rises from 50% to 57%.
  - **vs IA:** the decoder-level form of "this step must write": the harness ends
    deliberation; it does not ask the model to.
- **Runaway is Ashamed, But Helpful: On the Early-Exit Behavior of LLM-based
  Agents in Embodied Environments.** Lu et al. Findings of EMNLP 2025.
  [arXiv:2505.17616](https://arxiv.org/abs/2505.17616)
  - **Mechanism:** embodied agents get stuck in repetitive loops. An injected or
    externally verified early exit cuts redundant steps at little cost, and
    handing over to a stronger agent after the exit does better within the same
    total budget.
  - **vs IA:** an exit plus a hand-off, which is a frame returning to its parent
    early.
- **Agentic Abstention: Do Agents Know When to Stop Instead of Act?** Luo, Wen,
  Wang. 2026. [arXiv:2606.28733](https://arxiv.org/abs/2606.28733)
  - **Mechanism:** 13 agent systems, more than 28,000 tasks. Agents either never
    stop or stop only after unneeded interactions, and larger models are
    sometimes worse. Distilled stopping rules raise timely recall from 26.7% to
    57.4% for Llama-3.3-70B.
- **SWE-agent's autosubmit** (§1.7.2): at the cost limit it submits the current
  diff rather than discarding it. This bears on 0.0.8e §4.4, the three frames
  that progressed on every step and still returned nothing.

**Escalate to the parent.**

- **Magentic-One: A Generalist Multi-Agent System for Solving Complex Tasks.**
  Fourney et al. (Microsoft). 2024.
  [arXiv:2411.04468](https://arxiv.org/abs/2411.04468)
  - **Mechanism:** an Orchestrator keeps a *task ledger* (facts, guesses, plan)
    and, every turn, a *progress ledger* answering five questions, including "Is
    the team looping or repeating itself?" and "Is forward progress being made?".
    A stall counter rises on a no. While it stays at or below 2 the team acts;
    above that, the Orchestrator leaves the inner loop, reflects, rewrites the
    task ledger and replans. AutoGen's `MagenticOneGroupChat` defaults to
    `max_stalls=3`.
  - **vs IA:** the closest published analogue of the stall streak and the ledger,
    down to the name. Its response is **escalation to a replanner**, not a notice
    and not withdrawal. That is the tier 0.0.8d §10.6 argues for, where the frame
    should have spawned and did not. Its progress test is an LLM judgement, so it
    could notice "writing the wrong thing", but it can also be talked round.
- **Plan-and-Act.** Erdogan et al. ICML 2025.
  [arXiv:2503.09572](https://arxiv.org/abs/2503.09572)
  - **Mechanism:** a planner rewrites the plan after *every* executor step.
    Dynamic replanning adds 10.3 points on WebArena-Lite.
  - **vs IA:** the executor never holds a long budget on its own.

**Restart warm.**

- **Optimal speedup of Las Vegas algorithms** (Luby, Sinclair, Zuckerman, *IPL*
  47(4), 1993) and **Heavy-tailed phenomena in satisfiability and constraint
  satisfaction problems** (Gomes, Selman, Crato, Kautz, *J. Automated Reasoning*
  24, 2000) *[citation-level]*
  - **Mechanism:** search runtimes are heavy-tailed, and rapid restarts remove
    the tail. Luby's universal sequence 1, 1, 2, 1, 1, 2, 4, … is optimal up to a
    constant among universal strategies.
  - **vs IA:** the theory behind Cursor's "periodic fresh starts" (§1.3). A frame
    on step 58 of a stall is in the tail.
- **Fail-Fast, Restart-Smart: Early Failure Prediction and Restart for SWE
  Agentic Tasks.** Wang, …, Lo. 2026.
  [arXiv:2608.03222](https://arxiv.org/abs/2608.03222)
  - **Mechanism:** a 0.6B monitor predicts failure from a trajectory prefix. On a
    trigger, the same policy restarts with fresh history and the interrupted
    repository diff available as an option. At a 5% false-positive target it
    saves 14.6–20.4% of tokens. With restarts, Qwen3.6-27B goes from 66.6% to
    71.8% on SWE-bench Verified.
  - **vs IA:** a warm restart (context dropped, disk kept) is close to IA's own
    shape. IA's frames already keep nothing but registers and disk, so a restart
    is mostly clearing the registers.
- **Why Retrying Fails: Context Contamination in LLM Agent Pipelines.** Yang.
  2026. [arXiv:2605.08563](https://arxiv.org/abs/2605.08563)
  - **Mechanism:** on SWE-bench Verified, independent retries predict 98.6%
    success at three attempts; the observed rate is 81.2%. A contaminated retry
    errs at 7.1 times the baseline.
  - **vs IA:** supports clearing context. It also warns that a stalled frame's
    own notes on disk can be the contaminant.
- **The Debugging Decay Index** (§1.7.1) gives the point at which to restart.

**Budgets a frame can see, and a parent can split.** These address 0.0.8e §4.4:
allocation is now the largest cause of failure.

- **Budget-Aware Tool-Use Enables Effective Agent Scaling (BATS).**
  (Google). 2025. [arXiv:2511.17006](https://arxiv.org/abs/2511.17006)
  - **Mechanism:** a budget tracker after every tool call ("Tool Budget Used: ##,
    Remaining: ##"), with guidance tiered by remaining budget, down to "avoid the
    tool" below 10%. BrowseComp with Gemini-2.5-Pro: 24.6% against ReAct's 12.6%
    at budget 100. Raising the budget does not help agents that cannot see it.
- **Are LLM Agents Budget-Aware? (BAGEN).** Lin et al. 2026.
  [arXiv:2606.00198](https://arxiv.org/abs/2606.00198)
  - **Mechanism:** frontier models are "consistently over-optimistic" about
    remaining budget and keep spending on tasks likely to fail. Even after
    training, interval coverage is 47%.
  - **vs IA:** parents cannot estimate children's step counts, and neither can
    trained models. That argues for budgets that can be renewed or escalated,
    not for better up-front guesses.
- **ZEBRA: Zero-shot Budgeted Resource Allocation for LLM Orchestration.** Hamri,
  Talgam-Cohen. 2026. [arXiv:2605.20485](https://arxiv.org/abs/2605.20485)
  - **Mechanism:** the LLM estimates a utility curve per phase, and the split is
    solved as a knapsack problem by water-filling. At half the spend it recovers
    94.4% of quality on APPS, against 88.1% when the LLM allocates directly.
  - **vs IA:** the parent estimates and an algorithm allocates, instead of the
    parent naming a step count.
- **Token-Budget-Aware LLM Reasoning (TALE).** Han et al. 2024.
  [arXiv:2412.18547](https://arxiv.org/abs/2412.18547)
  - **Mechanism:** a budget in the prompt cuts output by about two-thirds, but
    below some budget cost goes *up* ("token elasticity") as the model stops
    complying.
  - **vs IA:** a constraint that is too tight gets ignored.
- **Principles of Metareasoning** (Russell, Wefald, *AIJ* 49, 1991) and **Using
  Anytime Algorithms in Intelligent Systems** (Zilberstein, *AI Magazine* 17(3),
  1996) *[citation-level]*
  - **Mechanism:** a computation step is worth taking only if it is expected to
    improve the next external action. Anytime algorithms trade deliberation for
    quality and allocate time across components.
  - **vs IA:** in these terms the seventeenth read of `smoke.py` has zero value
    of computation. Children's budgets are a contract-allocation problem.

**Progress a digest cannot fake.** These address 0.0.8e §4.5: writing is
progress by definition, so the stall measure cannot see a frame writing the wrong
thing.

- **AgentPRM** (Xi et al. 2025, [arXiv:2511.08325](https://arxiv.org/abs/2511.08325))
  and **Process Reward Models for LLM Agents** (Choudhury 2025,
  [arXiv:2502.10325](https://arxiv.org/abs/2502.10325))
  - **Mechanism:** learned step-level scores. Xi et al. score *promise* and
    *progress* (the change in value between steps). Choudhury trains PRMs from
    rollouts and discusses reward hacking.
  - **vs IA:** "the value went up" is the principled replacement for "a file
    changed". Choudhury's reward-hacking caveat applies to any judge of progress,
    including Magentic-One's.
- **Intelligent Go-Explore.** Lu, Hu, Clune. ICLR 2025.
  [arXiv:2405.15143](https://arxiv.org/abs/2405.15143)
  - **Mechanism:** an archive of interesting states. A foundation model chooses
    which one to return to and judges whether new ones are worth keeping. It
    succeeds where Reflexion fails.
  - **vs IA:** the response to being stuck is to return to an earlier good state
    and branch, not to try harder from here. Count-based exploration (Bellemare
    et al. 2016, [arXiv:1606.01868](https://arxiv.org/abs/1606.01868)) is the
    soft version: a bonus for novelty. IA's results on prices suggest a soft bonus
    works only when trained into the policy.

#### 1.7.6 What this means for 0.0.9

- **Withdrawal has more support than any notice.** Masking scales where
  penalties do not (Huang & Ontañón). Gating tools by state raised success
  (StateFlow, Agent-C). An interface change moved overthinking where prompts did
  not (Cuadron). Loops come from an easy cyclic action being available (Pipis et
  al.). No production agent found withdraws a *class* of tool on a stall, so this
  would be new.
- **Forbid the class, with an exception.** Tabu search's lesson: forbid
  read-only steps, not a list of exact repeats, and lift the ban when something
  moves. Keep the schema stable with a harness refusal or a group mask (Manus).
  Name the admissible moves in the refusal (Agent-C).
- **The ledger's wording may be part of the problem.** *Feedback That Backfires*
  finds that the verbatim surface form of a failed call drives its repetition,
  and that a runtime-written description removes most of the effect. The ledger
  names `smoke.py x16` verbatim. Xing et al. is the counter-evidence. Rewording
  is a cheap A/B, but it must ship separately from withdrawal (0.0.8d §7.1).
- **Point at a location, not a duration** (Tyen et al.): the failing assertion
  and the call site, not the step count.
- **"Fixed" belongs to the check** (the progress mirage, false success, the
  hallucination snowball). 0.0.8e §2.3 already draws this line. The literature
  says to keep it.
- **If withdrawal fails, the next tiers are already published:** escalate to the
  parent after a few stalls (Magentic-One), or restart the frame warm with disk
  kept (FailFast–RestartSmart, Luby and Gomes).
- **Withdrawal does not touch two holes.**
  - *Allocation*: budget estimates are poorly calibrated even after training
    (BAGEN). The literature's answers are visible remaining budget (BATS),
    algorithmic splitting (ZEBRA) and banking partial work at the limit
    (SWE-agent).
  - *Writing the wrong thing*: only a learned or judged progress signal reaches
    it (AgentPRM, Magentic-One's progress question, Intelligent Go-Explore), and
    each can be gamed.

---

## 2. Keeping the context small at all times

### 2.1 Evidence that the effective context is much smaller than the window

This is the motivation for "keep it small", as opposed to "fill it, then
compact".

| work | finding | link |
| --- | --- | --- |
| **Lost in the Middle**: Liu et al., TACL 2024 | accuracy is U-shaped in the position of the evidence; the middle of a long context is used worst | [2307.03172](https://arxiv.org/abs/2307.03172) |
| **RULER**: Hsieh et al. (NVIDIA), COLM 2024 | coined "effective context length"; only about half of the models claiming ≥32K stay satisfactory at 32K | [2404.06654](https://arxiv.org/abs/2404.06654) |
| **NoLiMa**: Modarressi et al., ICML 2025 | needle tests without literal overlap: at 32K, 11 of 13 models claiming ≥128K fall to half their short-context score (GPT-4o: 99.3% → 69.7%) | [2502.05167](https://arxiv.org/abs/2502.05167) |
| **Context Rot**: Hong, Troynikov, Huber (Chroma), 2025 | across 18 models, reliability falls at every length step, even on trivial copying; worse with distractors | [report](https://www.trychroma.com/research/context-rot) |
| **Same Task, More Tokens**: Levy, Jacoby, Goldberg, ACL 2024 | the same QA padded longer: reasoning drops by about 3K tokens (0.92 → 0.68) | [2402.14848](https://arxiv.org/abs/2402.14848) |
| **Context Length Alone Hurts LLM Performance Despite Perfect Retrieval**: Du et al., Findings of EMNLP 2025 | drops of 13.9% to 85% with length **even when the filler is whitespace or masked from attention**; "recite, then solve" converts it back to a short task | [2510.05381](https://arxiv.org/abs/2510.05381) |
| **LLMs Get Lost in Multi-Turn Conversation**: Laban, Hayashi et al., 2025 | −39% average multi-turn against single-turn; early wrong assumptions get locked in | [2505.06120](https://arxiv.org/abs/2505.06120) |
| **Unable to Forget: Proactive Interference…**: Wang, Sun, 2025 | retrieving a key's *latest* value falls log-linearly to zero as earlier updates accumulate, independent of length; prompting does not fix it | [2506.08184](https://arxiv.org/abs/2506.08184) |
| **The Illusion of Diminishing Returns**: Sinha et al., ICLR 2026 | "**self-conditioning**": models err more when their own earlier errors are in context, and scale does not fix it | [2509.09677](https://arxiv.org/abs/2509.09677) |
| **BABILong**: Kuratov et al., NeurIPS 2024 D&B | LLMs effectively use 10–20% of their context; a small recurrent-memory model reaches 11M tokens | [2406.10149](https://arxiv.org/abs/2406.10149) |
| **LongBench v2**: Bai et al., ACL 2025 | 8K–2M words; best direct answer 50.1%, human experts 53.7% | [2412.15204](https://arxiv.org/abs/2412.15204) |
| **HELMET**: Yen et al., ICLR 2025 | needle-in-a-haystack scores do not predict downstream long-context performance | [2410.02694](https://arxiv.org/abs/2410.02694) |
| **Michelangelo**: Vodrahalli et al. (GDM), 2024 | tracking a latent structure (for example a list under operations) degrades early | [2409.12640](https://arxiv.org/abs/2409.12640) |
| **LongICLBench**: Li et al., TMLR 2025 | models collapse on many-label in-context learning at long lengths | [2404.02060](https://arxiv.org/abs/2404.02060) |
| **GSM-∞**: Zhou et al., ICML 2025 | performance follows a sigmoid in complexity; exponentially more compute buys linear gains | [2502.05252](https://arxiv.org/abs/2502.05252) |
| **Fiction.LiveBench**, 2025–26 | deep story comprehension decays well before the maximum window | [leaderboard](https://fiction.live/stories/Fiction-liveBench-Feb-21-2025/oQdzQvKHw8JyXbN87) |
| **Lost in Compaction**: Wang et al., 2026 | compactors keep only about 17% of user side-constraints; a dedicated extractor gets over 90% | [2608.11242](https://arxiv.org/abs/2608.11242) |

**What this means for IA:**

- Three rows argue directly for **stateless steps**: proactive interference,
  self-conditioning and multi-turn lock-in. A transcript accumulates stale values
  and the agent's own errors; a register overwritten in place does not.
- *Same Task, More Tokens* and *Context Length Alone* show degradation at a few
  thousand tokens. So IA's ~8K request is not automatically "small enough", and
  shrinking the fixed half (`--short`) has a reason beyond cost.
- *Lost in Compaction* measures the **width** axis: constraints that must stay
  true at once are what compaction drops.

### 2.2 Inference-time methods with a bounded context (no training)

- **RecurrentGPT: Interactive Generation of (Arbitrarily) Long Text.** Zhou et
  al. 2023. [arXiv:2305.13304](https://arxiv.org/abs/2305.13304)
  - **Mechanism:** imitates an LSTM in natural language. Each step sees a
    short-term memory paragraph, retrieved long-term memory and a plan, then
    writes the next paragraph and updated memories. Shape: **constant**.
  - **vs IA:** the earliest explicit **infinite-writing** scaffold, and nearly
    register 3 + register 4 + register 2. It is a fixed loop with no tools or
    recursion.
- **SCM: Self-Controlled Memory Framework.** Wang et al. 2023.
  [arXiv:2304.13343](https://arxiv.org/abs/2304.13343)
  - **Mechanism:** each step sees the current segment, a "flash memory" of the
    previous one and selectively retrieved "activation memory". Shape:
    **constant**.
  - **vs IA:** the last-step record plus the summary, structurally.
- **PRISM: Efficient Long-Range Reasoning With Short-Context LLMs.** Jayalath et
  al. (Google). EMNLP 2025. [arXiv:2412.18914](https://arxiv.org/abs/2412.18914)
  - **Mechanism:** streams chunks and keeps a *typed, hierarchical* memory that
    the model revises. Matches baselines with 4× shorter contexts. Shape:
    **constant**.
  - **vs IA:** typed slots are the registers, and PRISM's finding that structure
    beats free text argues for registers over a single summary.
- **Chain of Agents.** Zhang et al. (Google). NeurIPS 2024.
  [arXiv:2406.02818](https://arxiv.org/abs/2406.02818)
  - **Mechanism:** workers read chunks in sequence and pass a bounded
    "communication unit"; a manager writes the answer. Up to +10% over RAG and
    full context.
  - **vs IA:** IA's 39MB reads, but as a fixed pipeline instead of self-directed
    steps.
- **LongAgent.** Zhao et al. 2024. [arXiv:2402.11550](https://arxiv.org/abs/2402.11550)
  - **Mechanism:** a leader plus chunk-holding members that resolve conflicts
    among themselves. Fixed fan-out.
- **MemWalker: Walking Down the Memory Maze.** Chen et al. (Meta). 2023.
  [arXiv:2310.05029](https://arxiv.org/abs/2310.05029)
  - **Mechanism:** navigates a precomputed summary tree from the root to a leaf,
    with backtracking. Shape: constant per step.
- **ReadAgent.** Lee et al. (GDM). ICML 2024.
  [arXiv:2402.09727](https://arxiv.org/abs/2402.09727)
  - **Mechanism:** compresses pages into gists and looks up the originals on
    demand. Shape: **slower**, because the gist list grows with the document.
  - **vs IA:** paged `load` without the growing gist list.
- **Writing in the Margins.** Russak et al. 2024.
  [arXiv:2408.14906](https://arxiv.org/abs/2408.14906)
  - **Mechanism:** per-chunk margin notes during prefill. The full KV cache
    remains, so shape: slower.
- **Sculptor: Active Context Management.** Li et al. (MSR). 2025.
  [arXiv:2508.04664](https://arxiv.org/abs/2508.04664)
  - **Mechanism:** tools to fragment, summarise, hide, restore and search one's
    own context, framed against proactive interference.
- **Context as an Environment (Scroll).** Lin, Ang, Zhu, Ding, Zhou (Alibaba).
  2026. [arXiv:2608.21690](https://arxiv.org/abs/2608.21690)
  - **Mechanism:** an append-only event log plus a persistent Python kernel.
    Tool outputs bind to variables instead of entering the prompt, and stale spans
    are evicted near the budget but stay recoverable through landmarks.
  - **vs IA:** very close to registers-as-files; Scroll keeps a lossless log
    index, while IA records only the last step automatically.
- **Beyond Compaction: Structured Context Eviction (CWL).** Semenov, Dorofeev.
  2026. [arXiv:2606.11213](https://arxiv.org/abs/2606.11213)
  - **Mechanism:** typed episodes with dependency links, evicted in priority
    order near a ceiling.
- **Self-GC: Self-Governing Context for Long-Horizon LLM Agents.** Hao et al.
  2026. [arXiv:2607.00692](https://arxiv.org/abs/2607.00692)
  - **Mechanism:** context items as indexed objects with lifecycles. It prunes
    43.95% of prefix tokens while leaving 84.85% of future continuations
    unaffected.
  - **vs IA:** garbage collection on a transcript; IA avoids needing one by
    keeping no transcript.
- **RLM, THREAD, TIM, RAH**: see §1.2.

### 2.3 Training methods (mostly RL) for bounded-context agents

Training the model to *live in* a bounded state is the main thing the literature
has that IA does not.

- **MEM1: Learning to Synergize Memory and Reasoning for Efficient Long-Horizon
  Agents.** Zhou et al. 2025. [arXiv:2506.15841](https://arxiv.org/abs/2506.15841)
  - **Mechanism:** each turn the model rewrites one compact internal state and
    drops every earlier turn; RL teaches what to keep. Shape: **constant**.
  - On 16-objective multi-hop QA, MEM1-7B scores 3.5× better than Qwen2.5-14B
    with 3.7× less memory, and generalises past its training horizon.
  - **vs IA:** the closest trained counterpart of a stateless step over carried
    state. MEM1 keeps one learned free-text blob; IA keeps structured,
    partly system-written registers, untrained.
- **MemAgent: Reshaping Long-Context LLM with Multi-Conv RL-based Memory
  Agent.** Yu et al. (ByteDance Seed, Tsinghua). ICLR 2026 *[venue unverified]*.
  [arXiv:2507.02259](https://arxiv.org/abs/2507.02259)
  - **Mechanism:** reads in fixed chunks and *overwrites* a fixed-length memory
    after each. Trained at 8K, it extrapolates to 3.5M-token QA with under 10%
    loss. Shape: **constant**, with linear time.
  - **vs IA:** proof that a fixed window plus overwritten memory reads anything,
    which is IA's reading clause. It cannot write output or decompose tasks.
- **The Markovian Thinker (Delethink).** Aghajohari et al. (Mila, McGill).
  ICLR 2026. [arXiv:2510.06557](https://arxiv.org/abs/2510.06557)
  - **Mechanism:** reasoning in fixed chunks (for example 8K). At each boundary
    the context resets to the query plus a short carryover, and RL teaches a
    sufficient "Markovian state". At 96K thinking length, training costs 7
    H100-months against 27 for standard long-chain-of-thought RL. Shape:
    **constant**.
  - **vs IA:** conceptually the nearest match. Delethink resets every N thinking
    tokens; IA resets every tool step, and its state is structured and
    addressable.
- **InftyThink** ([arXiv:2503.06692](https://arxiv.org/abs/2503.06692),
  ICLR 2026) and **InftyThink+** ([arXiv:2602.06960](https://arxiv.org/abs/2602.06960),
  ICML 2026). Yan et al.
  - **Mechanism:** think, summarise, discard all but the summary. Shape:
    sawtooth. InftyThink+ learns, with RL, when to summarise and what to keep.
  - **vs IA:** register 4 for a single chain of thought.
- **PENCIL**: see §1.2. It is also a training method, with learned reductions.
- **ReSum: Unlocking Long-Horizon Search Intelligence via Context
  Summarization.** Wu et al. (Alibaba Tongyi). 2025.
  [arXiv:2509.13313](https://arxiv.org/abs/2509.13313)
  - **Mechanism:** periodically turns the ReAct history into a reasoning state;
    ReSum-GRPO trains the agent to continue from it. +4.5% over ReAct, and +8.2%
    after training. Shape: sawtooth.
  - **vs IA:** fill-then-compact, the opposite discipline, and a natural baseline.
- **SUPO: Scaling LLM Multi-turn RL with End-to-end Summarization-based Context
  Management.** Lu et al. (ByteDance Seed, Stanford, CMU). 2025.
  [arXiv:2510.06727](https://arxiv.org/abs/2510.06727)
  - **Mechanism:** a policy gradient over tool use and summarisation jointly.
    +14.0% on BrowseComp-Plus with a **64K** working context, about 8× IA's.
- **Context-Folding** and **AgentFold**: see §1.2.
- **Memory as Action (MemAct).** Zhang et al. 2025.
  [arXiv:2510.12635](https://arxiv.org/abs/2510.12635)
  - **Mechanism:** context deletion and insertion are policy actions; average
    context is 51% shorter.
- **ACON: Optimizing Context Compression for Long-horizon LLM Agents.** Kang et
  al. (Microsoft). ICML 2026. [arXiv:2510.00615](https://arxiv.org/abs/2510.00615)
  - **Mechanism:** refines the *compression instructions* in natural language
    from failure cases, then distils them into a small compressor. Peak tokens
    fall 26–54%.
  - **vs IA:** directly applicable to register 4's summariser prompt, with no
    weight changes needed.
- **ContextBudget: Budget-Aware Context Management for Long-Horizon Search
  Agents.** Wu et al. 2026. [arXiv:2604.01664](https://arxiv.org/abs/2604.01664)
  - **Mechanism:** compression as sequential decisions under an explicit budget,
    with a tightening budget curriculum.
- **Memex(RL)**: see §1.1.
- **Briefly:**
  - **Mem-α** ([arXiv:2509.25911](https://arxiv.org/abs/2509.25911)): RL over
    core, episodic and semantic memory; trained at 30K, it generalises beyond
    400K.
  - **ReMemR1** ([arXiv:2509.23040](https://arxiv.org/abs/2509.23040)): a
    MemAgent that can revisit earlier memories.
  - **UMA, "Learning to Remember"** (Zhang et al. 2026,
    [arXiv:2602.18493](https://arxiv.org/abs/2602.18493)): a core summary plus a
    key-value bank with CRUD operations. Its **Ledger-QA** task tracks
    accumulated updates, the same problem as 0.0.8e's "memory that can count".
  - **ACM: Agentic Context Management** (Li et al. 2026,
    [arXiv:2607.23809](https://arxiv.org/abs/2607.23809)): context-editing
    tools plus external storage of discarded content.

### 2.4 Context-engineering practice

- **Effective context engineering for AI agents.** Anthropic, 2025-09-29.
  [link](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  - **Mechanism:** context is a finite "attention budget". It recommends the
    smallest high-signal token set, just-in-time retrieval by identifiers
    (paths), compaction, structured notes outside the window, and sub-agents with
    clean contexts returning 1–2K-token summaries.
  - **vs IA:** IA takes all of this to the limit: compaction every step, notes in
    registers, and recursive sub-agents.
- **Managing context on the Claude Developer Platform.** Anthropic, 2025-09-29.
  [link](https://www.anthropic.com/news/context-management)
  - **Mechanism:** context editing clears stale tool results, and a file-based
    memory tool persists across sessions. +39% and 84% fewer tokens on a 100-turn
    evaluation. Still a trimmed transcript.
- **Context Engineering for AI Agents: Lessons from Building Manus.** Ji
  (Manus), 2025-07-18.
  [link](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
  - **Mechanism:**
    - the file system is unlimited context;
    - compression must be *restorable* (drop the content, keep the path);
    - the agent "recites" its goal by rewriting `todo.md`;
    - keep errors in context;
    - design for KV-cache hit rate, given a roughly 100:1 input-to-output ratio.
  - **vs IA:** disk state and the target register mirror Manus's files and
    `todo.md`. The real trade-off is the cache: Manus keeps an append-only
    transcript for cache hits, and IA's stateless steps give that up beyond the
    static half (system message and tool schemas).
- **Context Engineering for Agents.** LangChain (Lance Martin), 2025.
  [link](https://www.langchain.com/blog/context-engineering-for-agents)
  - **Mechanism:** a taxonomy of write, select, compress and isolate.
  - **vs IA:** registers and disk are write, `load` is select, register 4 is
    compress, and `spawn` is isolate.
- **The Complexity Trap: Simple Observation Masking Is as Efficient as LLM
  Summarization for Agent Context Management.** Lindenbauer et al. (JetBrains).
  NeurIPS 2025 DL4Code workshop. [arXiv:2508.21433](https://arxiv.org/abs/2508.21433)
  - **Mechanism:** in SWE-agent, masking old observations halves cost and matches
    or beats LLM summarisation; with Qwen3-Coder 480B it is 52% cheaper and solves
    2.6% more.
  - **vs IA:** a cheap baseline IA should beat or match. It also suggests that
    summariser quality matters less than assumed, which is consistent with 0.0.6
    moving register 4 to a small model at no effort.

### 2.5 Architecture-level contrasts (these change the model, not the agent)

These bound memory *inside the network*, as lossy, unreadable state with no
tools. IA gets its bound with any off-the-shelf model, and its state is plain
text that can be inspected and edited.

- **Mamba**: Gu, Dao 2023, [arXiv:2312.00752](https://arxiv.org/abs/2312.00752).
  A constant recurrent state, weak at precise recall.
- **Recurrent Memory Transformer**: Bulatov, Kuratov, Burtsev, NeurIPS 2022,
  [arXiv:2207.06881](https://arxiv.org/abs/2207.06881). The model behind
  BABILong's 11M-token result.
- **Infini-attention**: Munkhdalai et al. 2024,
  [arXiv:2404.07143](https://arxiv.org/abs/2404.07143).
- **StreamingLLM (attention sinks)**: Xiao et al., ICLR 2024,
  [arXiv:2309.17453](https://arxiv.org/abs/2309.17453).
- **KV-cache eviction:**
  - **H2O**: Zhang et al., NeurIPS 2023,
    [arXiv:2306.14048](https://arxiv.org/abs/2306.14048).
  - **SnapKV**: Li et al., NeurIPS 2024,
    [arXiv:2404.14469](https://arxiv.org/abs/2404.14469).
  - **InfiniPot**: Kim et al., EMNLP 2024,
    [arXiv:2410.01518](https://arxiv.org/abs/2410.01518).
- **HOMER**: Song et al., ICLR 2024,
  [arXiv:2404.10308](https://arxiv.org/abs/2404.10308). Memory logarithmic in
  length.
- **LongMem**: Wang et al., NeurIPS 2023,
  [arXiv:2306.07174](https://arxiv.org/abs/2306.07174).
- **MemoRAG**: Qian et al., WWW 2025,
  [arXiv:2409.05591](https://arxiv.org/abs/2409.05591).

---

## 3. Benchmarks for arbitrarily long-horizon tasks

Grouped by the [Infinite Context Test](docs/Design%20Tests%20(Top%20Down).md)
clause each one serves.

**Fit** is how well the benchmark matches the CLI shape,
`infinite "<instr>" -w ws --schema … --check …`:

- **file**: a text or file corpus in the workspace (good);
- **venv**: a repository plus a Python environment, as SWE-bench already uses;
- **Docker**: a per-task container;
- **sim**: a simulator to expose as bash commands;
- **GUI**: a browser, desktop or game environment.

**Effort** is L, M or H.

**Already in use:** BABILong, ∞Bench and SWE-bench Verified
([Evaluation](docs/Evaluation.md)), plus the project's own `width`, `volume` and
the Reconstruction Test. [Standard
Evaluations](docs/Standard%20Evaluations.md) lists four gaps, and this section
marks which benchmarks fill them:

- **G1**: a correctness-graded writing probe whose content a script cannot
  derive;
- **G2**: a computational-completeness probe;
- **G3**: a stack-mode probe;
- **G4**: a reconstruction harness.

### 3.1 Infinite reading

| benchmark | scale | graded by | fit / effort | note |
| --- | --- | --- | --- | --- |
| **GSM-∞**: Zhou et al. 2025, [2502.05252](https://arxiv.org/abs/2502.05252), [code](https://github.com/Infini-AI-Lab/gsm_infinite) | unbounded on **both** reasoning ops and context length | exact number | file / L | dense, resistant to RAG; many interdependent quantities, so it is width-in-reading |
| **Oolong**: Bertsch et al. 2025, [2511.02817](https://arxiv.org/abs/2511.02817), [code](https://github.com/abertsch72/oolong) | synth (tunable) + real; under 50% for frontier models at 128K | exact / numeric | file / L | aggregation that needs a semantic judgement per item, so grep cannot do it; an RLM headline benchmark |
| **BrowseComp-Plus**: Chen et al. 2025, [2508.06600](https://arxiv.org/abs/2508.06600) | ~100K-document fixed corpus | short answer | file / L–M | deep research offline; used by RLM and SUPO |
| **LongBench v2**: [2412.15204](https://arxiv.org/abs/2412.15204) | 8K–2M words, 503 MC | exact letter | file / L | a stronger grader than ∞Bench free-form |
| **RULER**: [2404.06654](https://arxiv.org/abs/2404.06654) | any length | exact | file / L | variable tracking is a cheap width-in-reading probe |
| **NoLiMa**: [2502.05167](https://arxiv.org/abs/2502.05167) | needle without literal overlap | exact | file / L | **the** test of whether a grep-paging reader breaks |
| **LongReason**: Ling et al. 2025, [2501.15089](https://arxiv.org/abs/2501.15089) | expandable to any length | MC | file / L | |
| **CogniLoad**: Kaiser et al., ICLR 2026, [2509.18458](https://arxiv.org/abs/2509.18458) | separate knobs for difficulty, distractors and length | exact | file / L | factorial control, so length can be told apart from width |
| **MemoryAgentBench**: Hu, Wang, McAuley, ICLR 2026, [2507.05257](https://arxiv.org/abs/2507.05257) | streamed chunks | exact / F1 | file / L–M | FactConsolidation probes register 4 restating a stale fact |
| **PI-LLM**: Wang, Sun, [2506.08184](https://arxiv.org/abs/2506.08184), [code](https://github.com/zhuangziGiantfish/Unable-to-Forget) | an unbounded key-value update stream | exact | file / L | does disk state beat in-context interference? |
| **LongMemEval / V2**: Wu et al., ICLR 2025, [2410.10813](https://arxiv.org/abs/2410.10813); V2 [2605.12493](https://arxiv.org/abs/2605.12493) | V2: agent-trajectory histories up to **115M tokens** | exact / judge | file / L–M | the largest reading scale found |
| **LongCodeBench**: Rando et al., COLM 2025, [2505.07897](https://arxiv.org/abs/2505.07897) | 32K–1M token code bases | QA / repair | venv / M | Claude 3.5 Sonnet falls from 29% to 3% between 32K and 256K |
| HELMET [2410.02694](https://arxiv.org/abs/2410.02694) · LOFT [2406.13121](https://arxiv.org/abs/2406.13121) · Michelangelo [2409.12640](https://arxiv.org/abs/2409.12640) · NeedleBench [2407.11963](https://arxiv.org/abs/2407.11963) · LoCoMo [2402.17753](https://arxiv.org/abs/2402.17753) | ≤128K to 1M; LoCoMo about 9K | mixed | file / L | lower priority: capped length, or redundant with BABILong |

### 3.2 Infinite writing (gap G1)

`volume` grades every field, but a twenty-line regex wins it. What is missing is
output that needs a generation per unit.

| benchmark | scale | graded by | fit / effort | note |
| --- | --- | --- | --- | --- |
| **LongProc**: Ye et al. 2025, [2501.05414](https://arxiv.org/abs/2501.05414), [site](https://princeton-pli.github.io/LongProc) | procedural outputs up to 8K tokens; input scalable | deterministic | file / L | several tasks are script-derivable, the same weakness `volume` has |
| **LongWeave**: Zhang et al., Findings of EMNLP 2025, [2510.24345](https://arxiv.org/abs/2510.24345) | input up to 64K and output up to 8K, customisable | constraint verifiers | file / L–M | realistic and verifiable; regenerate at larger lengths |
| **LongGenBench**: Wu et al., ICLR 2025, [2409.02076](https://arxiv.org/abs/2409.02076) | 16K+ token outputs with positional constraints | partly rule-based | file / L | |
| LongWriter [2408.07055](https://arxiv.org/abs/2408.07055) · HelloBench [2409.16191](https://arxiv.org/abs/2409.16191) | 10K+ words | LLM judge | file / L | measures length and quality, not correctness; low value |

The strongest correctness-graded writing tests turn out to be the reconstruction
benchmarks in §3.6 (Commit0, NL2Repo, ProgramBench), where the output is code no
script can derive and held-out tests grade it.

### 3.3 Infinite complexity: width

These grade *behaviour at the seams*, which `width` (graded on import only)
cannot see.

| benchmark | scale | graded by | fit / effort | note |
| --- | --- | --- | --- | --- |
| **Breakpoint**: Hariharan, Girit, Wang, Andreas 2025, [2506.00172](https://arxiv.org/abs/2506.00172) | procedurally generated; a knob for the **number of simultaneously corrupted interdependent functions** and call-graph centrality | the repository's own tests | venv / M | width as a literal knob; up to 55% on single-function tasks and 0% on the hardest |
| **SWE-Bench Pro**: Deng et al. (Scale AI) 2025, [2509.16941](https://arxiv.org/abs/2509.16941) | multi-file patches taking hours to days | held-out tests | Docker / M | under 25% at release; the successor to Verified |
| **SWE-EVO**: 2025, [2512.18470](https://arxiv.org/abs/2512.18470) | ~21 files and ~874 tests per instance | tests | Docker / M | GPT-5 with OpenHands 21%, against 65% on Verified |
| **RoadmapBench**: 2026, [2605.15846](https://arxiv.org/abs/2605.15846) | median 3,700 lines across 51 files; 5 languages | weighted per-subtask tests | Docker / M–H | a gradient score rather than pass/fail |
| **FeatureBench**: ICLR 2026, [2602.10975](https://arxiv.org/abs/2602.10975) | features spanning many commits | tests | Docker / M | Claude Opus 4.5 11% |
| **SWE-Dev**: Du et al. 2025, [2505.16975](https://arxiv.org/abs/2505.16975) | 500 feature tasks | tests | venv / M | |
| **SlopCodeBench**: 2026, [2603.24755](https://arxiv.org/abs/2603.24755) | 196 checkpoints extending the agent's own code | tests plus erosion metrics | venv / M | width that accumulates over time, which is 0.0.8d's seams failure |
| **LoCoBench-Agent**: Qiu et al. (Salesforce) 2025, [2511.13998](https://arxiv.org/abs/2511.13998) | 10K–1M token code bases | partly heuristic or LLM | venv / M | weaker grading |

### 3.4 Computational completeness: the agent as CPU (gap G2)

| benchmark | scale | graded by | fit / effort | note |
| --- | --- | --- | --- | --- |
| **Long-Horizon Execution**: Sinha et al., ICLR 2026, [2509.09677](https://arxiv.org/abs/2509.09677), [code](https://github.com/long-horizon-execution/measuring-execution) | look up K keys per turn and keep a running sum; horizon K×T, unbounded | exact, every step | file / L | GPT-5 with thinking reached 2,176 steps, Claude 4 Sonnet 432. Self-conditioning predicts stateless steps should flatten error growth |
| **TMBench**: Wu, Han et al. 2025, [2504.20771](https://arxiv.org/abs/2504.20771), [code](https://github.com/HaitaoWuTJU/Turing-Machine-Bench) | step-by-step m-tag Turing-machine simulation; controllable | exact, every step | file / L | Turing completeness, literally |
| **FSM Execution**: Samiei et al. 2025, [2511.14777](https://arxiv.org/abs/2511.14777) | separate branching and horizon knobs | exact | file / L | branching hurts more than length |
| **CLRS-Text**: Markeeva et al. 2024, [2406.04229](https://arxiv.org/abs/2406.04229) | traces of 30 algorithms at any size | exact trace | file / L | the DFS and recursion traces double as stack probes |
| **R-HORIZON**: Lu et al., ICLR 2026, [2510.08189](https://arxiv.org/abs/2510.08189) | chained problems, each answer feeding the next | exact | file / L | depth of composition |
| **LongCoT**: Motwani et al. 2026, [2604.14140](https://arxiv.org/abs/2604.14140) | derivations of 10⁴–10⁵ tokens over step graphs | exact | file / L | best model under 10%; the derivation must be externalised |
| **Reasoning Gym**: Stojanovski et al., NeurIPS 2025, [2505.24760](https://arxiv.org/abs/2505.24760) | 100+ generators with adjustable difficulty | verifiers | file / L | a library to build scaled probes from |

**Caveat that applies to the whole group:** a script computes most of these, so
an unrestricted bash agent will write the script. That is a valid solution, but
it measures Python rather than the scaffold. Run one arm with interpreters denied,
or with the rules given only in prose, so that the model is the step function.

### 3.5 Stack mode without recursion (gap G3)

**No existing benchmark tests a stack the agent manages itself.** The closest
generators:

- **Tower of Hanoi / puzzle scaling**, from *The Illusion of Thinking* (Shojaee
  et al. (Apple) 2025, [arXiv:2506.06941](https://arxiv.org/abs/2506.06941)).
  - 2^N−1 moves at recursion depth N; reasoning models collapse at N=7–8.
  - The rebuttal *The Illusion of the Illusion of Thinking*
    ([arXiv:2506.09250](https://arxiv.org/abs/2506.09250)) shows that writing a
    program solves N=15.
  - So: disable `spawn` and code execution, and validate every move.
- **CLRS-Text DFS traces** and **Michelangelo's Latent List**: secondary
  state-tracking probes.

### 3.6 Reconstruction: build a system from a spec (gap G4)

| benchmark | scale | graded by | fit / effort | note |
| --- | --- | --- | --- | --- |
| **Commit0: Library Generation from Scratch**: Zhao et al., ICLR 2025, [2412.01769](https://arxiv.org/abs/2412.01769), [env](https://github.com/commit-0/commit0), [site](https://commit-0.github.io/) | 54 libraries (16 in *lite*); specs of **10K–300K tokens**; stub repo plus unit tests | unit-test pass rate | venv / M | the spec exceeds the context, as the condensed spec does; the tests are a ready-made `--check`; no agent fully reproduces any library |
| **NL2Repo-Bench**: Ding et al. 2025, [2512.12730](https://arxiv.org/abs/2512.12730), [code](https://github.com/multimodal-art-projection/NL2RepoBench) | 104 libraries from one spec (~18.8K tokens) into an **empty workspace**, tests hidden | upstream pytest | Docker / M | 70–275 turns; best under 40%; named failure modes (premature stop, architectural drift) are 0.0.8d's |
| **ProgramBench**: Yang, Lieret, …, Press 2026, [2605.03546](https://arxiv.org/abs/2605.03546), [code](https://github.com/facebookresearch/ProgramBench) | 200 programs from a binary plus docs, small CLI tools up to SQLite and FFmpeg; any language | fuzzing-derived behavioural tests | Docker / H | no model fully resolves a task; best passes 95% of tests on only 3% of tasks |
| **DeNovoSWE**: Zhao et al. 2026, [2606.10728](https://arxiv.org/abs/2606.10728) | 4,818 document-to-repository tasks | tests | Docker / M | built for training; a large pool for held-out samples |
| **PaperBench**: Starace et al. (OpenAI) 2025, [2504.01848](https://arxiv.org/abs/2504.01848) | 20 papers, runs up to 36h | LLM judge on rubrics | GPU / H | a weaker grader |
| **HANDBOOK.md**: Panavas et al. 2026, [2607.25398](https://arxiv.org/abs/2607.25398) | 20–124 page procedure documents; 824 criteria | deterministic | sim / M | a mechanical proxy for the Reconstruction Test's "faithful" gate, which now needs a person |
| ResearchCodeBench [2506.02314](https://arxiv.org/abs/2506.02314) · ProjectEval [2503.07010](https://arxiv.org/abs/2503.07010) · RE-Bench [2411.15114](https://arxiv.org/abs/2411.15114) | smaller | tests / scoring | mixed | |

### 3.7 Generality and coherence: runs that go until failure

| benchmark                                                                                                                                                                                       | scale                                                                 | graded by                  | fit / effort | note                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | -------------------------- | ------------ | ------------------------------------------------------------------------------------------ |
| **Vending-Bench** [2502.15840](https://arxiv.org/abs/2502.15840) / **Vending-Bench 2** ([site](https://andonlabs.com/evals/vending-bench-2))                                                    | >20M tokens; V2 is one simulated year, 3,000–6,000 messages           | final balance              | sim / M      | meltdown loops not tied to context saturation; whether the harness is public is unverified |
| **YC-Bench**: He et al. 2026, [2604.01212](https://arxiv.org/abs/2604.01212)                                                                                                                    | a simulated year, hundreds of turns                                   | final capital              | sim / M      | the **open** substitute for Vending-Bench; scratchpad use predicts success                 |
| **LOCA-bench**: Zeng, Huang, He 2026, [2602.07962](https://arxiv.org/abs/2602.07962), [code](https://github.com/hkust-nlp/LOCA-bench)                                                           | environment state grows "potentially to infinity" with the task fixed | automatic                  | sim / M      | **the Infinite Context claim stated as a benchmark**; scores model plus scaffold           |
| **AgentLongBench**: Fang et al. 2026, [2601.20730](https://arxiv.org/abs/2601.20730)                                                                                                            | 32K–4M token rollouts                                                 | automatic                  | sim / M      |                                                                                            |
| **UltraHorizon**: Luo et al. 2025, [2509.21766](https://arxiv.org/abs/2509.21766)                                                                                                               | 200K+ tokens, 400+ tool calls                                         | automatic                  | sim / M      | names "in-context locking"                                                                 |
| **AgencyBench**: GAIR, ACL 2026, [2601.11044](https://arxiv.org/abs/2601.11044)                                                                                                                 | ~90 tool calls and ~1M tokens per task                                | rubric plus simulated user | Docker / M   | partly judged                                                                              |
| **Terminal-Bench 2.0**: Merrill et al. 2026, [2601.11868](https://arxiv.org/abs/2601.11868), [site](https://www.tbench.ai/)                                                                     | 89 hard terminal tasks                                                | tests                      | Docker / L–M | a native fit for bash plus a workspace; cheap breadth                                      |
| **METR time horizons**: Kwa et al., NeurIPS 2025, [2503.14499](https://arxiv.org/abs/2503.14499); HCAST [2503.17354](https://arxiv.org/abs/2503.17354); [site](https://metr.org/time-horizons/) | tasks from 1 minute to 8h+                                            | algorithmic                | mixed / H    | adopt the **50% time-horizon metric** even without the tasks                               |
| **TextQuests**: Phan et al. 2025, [2507.23701](https://arxiv.org/abs/2507.23701)                                                                                                                | 25 Infocom games, 30h+ for humans                                     | progress                   | sim / M      | text-only; a cheap loop-resistance test                                                    |
| **BALROG**: Paglieri et al., ICLR 2025, [2411.13543](https://arxiv.org/abs/2411.13543)                                                                                                          | NetHack, TextWorld, Crafter… very long episodes                       | progress                   | sim / M      | use the text environments                                                                  |
| **Factorio Learning Environment**: Hopkins et al., NeurIPS 2025, [2503.09617](https://arxiv.org/abs/2503.09617)                                                                                 | open play is unbounded                                                | production score           | sim / M–H    | the agent acts by writing programs                                                         |

**Lower priority** (short horizons, GUI, or GPU-bound):

- **Short-horizon tool tasks:** AppWorld [2407.18901](https://arxiv.org/abs/2407.18901),
  τ²-bench [2506.07982](https://arxiv.org/abs/2506.07982),
  MCPMark [2509.24002](https://arxiv.org/abs/2509.24002),
  MCP-Universe [2508.14704](https://arxiv.org/abs/2508.14704),
  AgentBench [2308.03688](https://arxiv.org/abs/2308.03688).
- **Cross-task memory:** LifelongAgentBench [2505.11942](https://arxiv.org/abs/2505.11942),
  StreamBench [2406.08747](https://arxiv.org/abs/2406.08747).
- **Security:** Cybench [2408.08926](https://arxiv.org/abs/2408.08926).
- **GPU or browser:** MLE-bench [2410.07095](https://arxiv.org/abs/2410.07095),
  SWE-Lancer [2502.12115](https://arxiv.org/abs/2502.12115),
  SWE-bench Multimodal [2410.03859](https://arxiv.org/abs/2410.03859).
- **GUI or web:** OSWorld [2404.07972](https://arxiv.org/abs/2404.07972),
  WebArena [2307.13854](https://arxiv.org/abs/2307.13854),
  WorkArena++ [2407.05291](https://arxiv.org/abs/2407.05291),
  OdysseyBench [2508.09124](https://arxiv.org/abs/2508.09124),
  GAIA [2311.12983](https://arxiv.org/abs/2311.12983),
  BrowseComp [2504.12516](https://arxiv.org/abs/2504.12516). Use BrowseComp-Plus
  instead of BrowseComp.

### 3.8 Methodology worth adopting

- **Benchmarking the Residual: What Long-Horizon Evaluations Add Beyond Matched
  Short-Task Performance.** Peng et al. 2026.
  [arXiv:2607.27283](https://arxiv.org/abs/2607.27283)
  - **Mechanism:** the *horizon residual* is full-task success minus the success
    predicted from matched short stages.
  - **vs IA:** it formalises the project's split between probes that attribute
    and a reconstruction that decides.
- **METR's 50% time horizon.** A single number that is comparable across
  versions.

### 3.9 Shortlist: what to add next

| # | add | gap it fills | why |
| --- | --- | --- | --- |
| 1 | **Commit0** (lite split first) | G4, G1, and the width correctness hole | a ready-made reconstruction harness: a spec beyond the context, a stub repo as the workspace, `pytest` as `--check`. It grades the seams that 0.0.8d died on, and its output is code no script can derive. Mostly covered by the existing venv machinery |
| 2 | **NL2Repo-Bench** | G4 | the closest public form of the Reconstruction Test (empty workspace, one spec, hidden tests); its easy/medium/hard split by lines of code is a scaling axis |
| 3 | **Breakpoint** | width (§4.1 and §4.3 of Standard Evaluations) | width as a literal knob, real tests, and reproducible on a fresh clone. Run at 1, 2, 4 and 8 corrupted functions and check that the largest request holds still |
| 4 | **An execution probe** from Sinha et al., TMBench and FSM Execution | G2 | program or transition table on disk, `--max-steps none`, T = 10²…10⁴, every step graded, interpreters denied in one arm. Self-conditioning predicts a measurable win for stateless steps |
| 5 | **Tower of Hanoi with `spawn` and code execution off**, plus CLRS-Text DFS | G3 | there is no published stack benchmark; N = 10, 15, 20 with every move validated |
| 6 | **Oolong-synth turned into per-item labels** (N = 10³…10⁵), plus LongWeave | G1 | each label needs a semantic judgement, so generations must scale with output. Report generated characters against output bytes |
| 7 | **GSM-∞** | reading × width | extends the 18/18 reading result (BABILong, ∞Bench) from retrieval to many interdependent quantities, with separate knobs for length and complexity |
| 8 | **Oolong-real and BrowseComp-Plus, reported against RLM** | external comparison | the two benchmarks the closest published recursive scaffold reports on |
| 9 | **YC-Bench** (or Vending-Bench 2 / TextQuests) | ledger and stall | runs to failure, where the known failure is meltdown loops unrelated to context saturation |
| 10 | **LOCA-bench** | the whole claim | the environment grows without bound while the task stays fixed; show that `max_request_tokens` stays flat |

Honourable mentions:

- **Terminal-Bench 2.0**: cheap generality.
- **SWE-Bench Pro or RoadmapBench**: harder successors to SWE-bench Verified.
- **ProgramBench**: the long-run reconstruction ceiling.
- **HANDBOOK.md**: a mechanical proxy for the "faithful" gate.

**Baselines to report against,** from §1–2:

- observation masking (*The Complexity Trap*);
- fill-then-summarise (OpenHands condenser, ReSum-style);
- folding (Context-Folding);
- RLM.

---

## 4. Synthesis: where InfiniteAgent sits

### 4.1 Closest prior art

1. **The constant-state reset family**: Delethink, MEM1, MemAgent, InftyThink.
   RecurrentGPT and SCM are the training-free versions; the Ralph loop and
   Anthropic's long-running harness are the session-grain versions. All discard
   history and carry a small state.
2. **The recursion family**: RLM, Yang–Srebro–Li's *Recursive Models*, PENCIL,
   THREAD, Context-Folding and RAH. Sub-contexts are isolated, and only return
   values flow up.
3. **Bounded tier plus external store**: MemGPT/Letta, Memex, Scroll and PRISM.
   This is where the editable, addressable slots come from.
4. **Theory**: Schuurmans (2023) is the formal template. A bounded-context model
   plus read/write memory plus a loop is universal, and Cui et al. (2026) argue
   that context management decides the computational power.

### 4.2 What InfiniteAgent combines that none of them does together

- **The finest reset grain, with no training.** Every single tool step is a
  stateless call. The reset family resets per chunk, per summary or per session,
  and almost all of it needs RL to work.
- **Constant, not sawtooth.** Nearly every practical system lets a transcript grow
  to a threshold and then compacts or evicts it: ReSum, SUPO, OpenHands,
  Anthropic context editing, CWL, Self-GC, Scroll. Masking and AgentFold only
  grow more slowly.
- **Structured, partly system-written state** instead of one free-text carryover:
  a result pointer, a last-step record, a target changed only on purpose, a
  separate cheap summary, and registers that are files and can be copied without
  passing through a generation.
- **Recursion into the same scaffold, under a contract.** Goal, read, write and
  check are rendered into the child's system message; the check runs after every
  step; and children's steps are charged to the parent. THREAD, Context-Folding
  and RAH recurse, but none checks every step against an oracle.
- **Progress as a measured quantity, plus a counting ledger.** Prior detectors
  match surface repetition: every production detector checked except Gemini
  CLI's LLM judge hashes the tool call (§1.7.2). Only Dubey (2026) recounts
  deterministically, and only UMA's Ledger-QA tests counting as a memory problem.
  Magentic-One's progress ledger is the nearest match in name and shape, but its
  progress test is an LLM judgement.
- **A three-axis frame.** Almost all prior work targets *depth*: long inputs (RLM,
  MemAgent, ReadAgent) or long reasoning (Delethink, InftyThink). A few target
  *volume* (RecurrentGPT, the coding harnesses). *Width* is barely addressed;
  *Lost in Compaction* and Breakpoint are the only direct measurements found.

### 4.3 What the literature warns about this design

- **Whole-summary rewriting loses detail.** ACE ("context collapse"), AgentFold
  and *Lost in Compaction* all find that repeatedly rewriting a summary erodes
  it, and Context-Folding reports that folding beats rolling summarisation.
  Register 4 is exactly that regime. 0.0.8e's own finding (one defect restated in
  58 consecutive summaries, with its truth value flipped four times) is an
  instance. The mitigations in the literature are:
  - incremental or delta updates (ACE);
  - typed records (AgentFold, PRISM);
  - optimised compressor instructions (ACON);
  - deterministic recounts (Dubey; IA's ledger).
- **Sub-agents lose implicit decisions.** Cognition's "Don't Build Multi-Agents"
  predicts 0.0.8d's Reconstruction failure: ten modules written by four agents
  disagreed at seven signatures. Commit0, Breakpoint and SlopCodeBench grade
  exactly this.
- **Small is not automatically small enough.** *Same Task, More Tokens* and
  *Context Length Alone* see degradation at about 3K tokens, below IA's ~8K
  request.
- **A bounded context does not buy coherence.** Vending-Bench finds that failures
  are uncorrelated with context saturation. The check, the stall measure and the
  ledger are IA's answer, and long-running coherence benchmarks (YC-Bench,
  Vending-Bench 2) are where that answer would be tested.
- **A warning can feed the loop it names.** *Feedback That Backfires* finds that
  the verbatim surface form of a failed call drives its repetition, and frequency
  bias (Schmied et al.) pulls toward whatever the context mentions most. The
  `[Ledger]` line quotes the files being looped on (§1.7.3).
- **The cost of stateless steps is the KV cache.** Manus's ~100:1 input-to-output
  ratio is why production systems keep append-only transcripts. IA re-sends a
  fresh register dump every step and caches only the static half.

### 4.4 What the literature supports

- **Stateless steps against self-conditioning and interference.** Sinha et al.
  (models err more with their own errors in context), *Unable to Forget* (stale
  updates drown the latest value) and *LLMs Get Lost in Multi-Turn Conversation*
  (early assumptions lock in) all predict that a transcript hurts and a curated,
  overwritten state helps.
- **Recursion over summary-only memory.** Yang–Srebro–Li prove an exponential
  advantage in active context for isolated sub-contexts over any summarisation
  method, and PENCIL proves optimal space for erase-on-return.
- **Removing an action over pricing it.** Invalid-action masking scales where a
  penalty does not (Huang & Ontañón), state-gated tools raise success (StateFlow,
  Agent-C), and loops come from an easy cyclic action being available (Pipis et
  al.). This is the case for 0.0.8d §10.3's withdrawal tier (§1.7.5–1.7.6).
- **A verdict owned by the check.** The progress mirage, false-success and
  hallucination-snowball results (§1.7.4) all find that self-assessed progress
  is unreliable and that an external, early gate is what catches it.
- **Fixed windows can read anything.** MemAgent (8K window, 3.5M tokens), RMT on
  BABILong (11M) and RLM (10M+) all support the reading clause from independent
  directions.
