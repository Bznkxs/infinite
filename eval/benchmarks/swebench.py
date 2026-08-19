"""SWE-bench Verified — a real issue in a real repository, graded by its tests.

The instances come from `princeton-nlp/SWE-bench_Verified` over the public rows
API. Each one names a repository, a base commit, the issue text, a test patch,
and two lists of tests: `FAIL_TO_PASS`, which the fix must make pass, and
`PASS_TO_PASS`, which it must not break.

The agent gets the repository at the base commit and the issue, and nothing
about the tests — the test patch is applied by the grader, afterwards, outside
the workspace the agent could write to. Grading runs the repository's own test
suite in a virtualenv built for the instance, which works for the pure-Python
repositories and is why `SAFE_REPOS` exists: the official harness uses Docker
images per instance, and this harness deliberately does not.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..fetch import rows
from ..workspace import Instance

NAME = "swebench"
DATASET = "princeton-nlp/SWE-bench_Verified"
#: Repositories that install from source with no compiler and no system
#: libraries. Everything else needs the Docker harness this one replaces.
SAFE_REPOS = ("pallets/flask", "pylint-dev/pylint", "pytest-dev/pytest", "sympy/sympy",
              "psf/requests", "marshmallow-code/marshmallow", "sqlfluff/sqlfluff")
#: Instances older than this are not attempted. The dataset spans 2013 to 2023,
#: and a 2013 environment cannot be rebuilt from PyPI alone at any interpreter
#: this harness can install: `requests` of that vintage vendors a urllib3 that
#: 3.10 broke, its era-pinned pytest clashes with any modern setuptools, and
#: each fix uncovers the next. That is what the official Docker images are for.
#: Anything from 2022 on builds from the commit date and its own declarations.
SINCE = "2022"

TASK_TEMPLATE = """# Fix a bug in {repo}

`repo/` is {repo} at commit {commit}, exactly as it was when this issue was
filed. It is a real repository: far more code than fits in your canvas, so find
your way around it with `grep` and `load` rather than reading it.

## The issue

{problem}

## What to do

Change the code under `repo/` so that the issue is fixed. Work in the
repository; do not write a patch file to be applied later — edit the files.

Rules:
- Do not add, change or delete anything under `repo/tests/`, `repo/testing/` or
  any other test directory. Your fix is graded by tests you have not seen, and
  editing tests is the one thing that invalidates the run.
- Keep the change as small as the issue needs.
- The repository's own conventions win over your preferences.

Write your response file as JSON: `answer` is a one-line summary of the change,
`evidence` is the output of `git -C repo diff --stat`.
"""


def load(*, config: str = "test", offset: int = 0, count: int = 1,
         repos: tuple[str, ...] = SAFE_REPOS, since: str = SINCE, **_) -> list[Instance]:
    instances: list[Instance] = []
    scanned, page = 0, 100
    while len(instances) < count and scanned < 500:
        batch = rows(DATASET, "default", config, offset + scanned, page)
        if not batch:
            break
        scanned += len(batch)
        for row in batch:
            if repos and row["repo"] not in repos:
                continue
            if since and str(row.get("created_at", ""))[:4] < since:
                continue
            instances.append(
                Instance(
                    benchmark=NAME,
                    instance_id=row["instance_id"],
                    task=TASK_TEMPLATE.format(
                        repo=row["repo"],
                        commit=row["base_commit"][:12],
                        problem=row["problem_statement"].strip(),
                    ),
                    files={},  # the repository is cloned, not written
                    truth={
                        "repo": row["repo"],
                        "created_at": row.get("created_at"),
                        "base_commit": row["base_commit"],
                        "test_patch": row["test_patch"],
                        "fail_to_pass": json.loads(row["FAIL_TO_PASS"]),
                        "pass_to_pass": json.loads(row["PASS_TO_PASS"]),
                        "gold_patch": row["patch"],
                    },
                    max_steps=120,
                )
            )
            if len(instances) >= count:
                break
    return instances


def materialise(instance: Instance, workspace: Path) -> None:
    """Put the repository at its base commit inside the workspace."""
    repo = workspace / "repo"
    if repo.exists():
        shutil.rmtree(repo)
    url = f"https://github.com/{instance.truth['repo']}.git"
    subprocess.run(["git", "clone", "--quiet", url, str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "--quiet", instance.truth["base_commit"]], check=True)


def _run(command: list[str], cwd: Path, timeout: float = 1800.0) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)


#: Where a repository pins the versions its tests were written against. The
#: official harness solves this with a Docker image per instance; without one,
#: the next best thing is whatever the repository itself declares at that
#: commit — flask at 7ee9ceb7 needs pytest<8, because its conftest uses an API
#: pytest 8 removed, and a harness that installs the newest pytest reports the
#: gold patch as a failure.
TEST_REQUIREMENTS = (
    "requirements/tests.txt", "requirements/dev.txt", "test-requirements.txt",
    "requirements-dev.txt", "requirements/testing.txt",
)
TEST_EXTRAS = ("tests", "test", "dev", "testing")
#: SWE-bench Verified spans 2013 to 2023, and an interpreter is as much a part
#: of an instance's environment as its packages: `requests` at a 2013 commit
#: vendors a urllib3 that imports `collections.MutableMapping`, which 3.10
#: removed. The official harness pins this per instance in a Docker image; this
#: is the same decision made from the commit's date.
PYTHON_BY_YEAR = ((2019, "3.8"), (2021, "3.9"), (2022, "3.10"))
GRADE_PYTHON = "3.11"


def python_for(date: str | None) -> str:
    if not date:
        return GRADE_PYTHON
    year = int(date[:4])
    for until, version in PYTHON_BY_YEAR:
        if year < until:
            return version
    return GRADE_PYTHON


def commit_date(repo: Path) -> str | None:
    """When the base commit was made, as an ISO date.

    This is what makes an environment reproducible without a Docker image: every
    dependency is resolved as it was on that day. Flask at 7ee9ceb7 needs
    werkzeug < 3 and pytest < 8, and says so nowhere — it simply predates both.
    """
    shown = _run(["git", "show", "-s", "--format=%cI", "HEAD"], repo, timeout=60)
    if shown.returncode != 0 or not shown.stdout.strip():
        return None
    return shown.stdout.strip().split("T")[0]


def _install(repo: Path, python: Path) -> str | None:
    """Build the environment the tests were written for. Returns an error, or None."""
    date = commit_date(repo)
    era = ["--exclude-newer", f"{date}T23:59:59Z"] if date else []
    # The build backend must not be period-correct — a 2013 commit resolves
    # setuptools to a version no modern build isolation will accept, and the
    # install becomes unsatisfiable for a reason that has nothing to do with
    # the repository. So the tooling is installed new, and only the packages
    # the tests actually import are pinned to the era.
    _run(["uv", "pip", "install", "--python", str(python), "setuptools", "wheel"], repo)
    pip = ["uv", "pip", "install", "--python", str(python), "--no-build-isolation", *era]

    base = _run([*pip, "-e", "."], repo)
    if base.returncode != 0:
        # An era that cannot be built is worth knowing about, but a run graded
        # against today's dependencies is still worth more than no run.
        loose = _run(
            ["uv", "pip", "install", "--python", str(python), "--no-build-isolation", "-e", "."],
            repo,
        )
        if loose.returncode != 0:
            return f"install failed: {base.stderr[-400:]}"
        pip = ["uv", "pip", "install", "--python", str(python), "--no-build-isolation"]

    for name in TEST_REQUIREMENTS:
        if (repo / name).exists():
            _run([*pip, "-r", name], repo)
    for extra in TEST_EXTRAS:
        _run([*pip, "-e", f".[{extra}]"], repo)

    # An install can succeed and still not leave a test runner behind — a
    # requirements file from 2013 pins the library's own dependencies and
    # nothing else. What the grader needs is pytest, so that is what is checked.
    if _run([str(python), "-c", "import pytest"], repo).returncode != 0:
        for attempt in ([*pip, "pytest"], ["uv", "pip", "install", "--python", str(python), "pytest"]):
            _run(attempt, repo)
            if _run([str(python), "-c", "import pytest"], repo).returncode == 0:
                break
        else:
            return "no pytest could be installed for this instance"

    # An era-pinned wheel can install and still not import — `requests` at a
    # 2022 commit resolves a brotli whose C extension does not load here. The
    # environment is only real if the package under test imports, so when it
    # does not, the era bound is dropped and the run says so.
    package = _importable(repo)
    if package and _run([str(python), "-c", f"import {package}"], repo).returncode != 0:
        _run(["uv", "pip", "install", "--python", str(python), "--no-build-isolation", "-e", "."], repo)
        if _run([str(python), "-c", f"import {package}"], repo).returncode != 0:
            return f"the package under test does not import ({package})"
    return None


def _importable(repo: Path) -> str | None:
    """The module a repository is meant to expose, guessed from its layout."""
    for parent in (repo / "src", repo):
        for child in sorted(parent.glob("*/__init__.py")) if parent.exists() else []:
            name = child.parent.name
            if name not in ("tests", "test", "docs", "examples", "scripts"):
                return name
    return None


def grade(response: dict[str, Any] | None, truth: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
    """Apply the held-out test patch and run both test lists.

    The agent never saw the test patch and cannot have written to it: it is
    applied here, after the run, from the dataset.
    """
    if workspace is None:
        return {"correct": False, "error": "no workspace to grade"}
    # Every path handed to a subprocess is absolute: these commands run with
    # cwd inside the repository, and a relative path would resolve there.
    workspace = workspace.resolve()
    repo = workspace / "repo"
    if not repo.exists():
        return {"correct": False, "error": "no repo/ in the workspace"}

    patch = workspace.parent / f"{workspace.name}.test.patch"
    patch.write_text(truth["test_patch"], encoding="utf-8")
    # Reset every file the test patch touches to the base commit before applying
    # it. This is what the official harness does, and it makes grading both
    # idempotent and immune to an agent that edited the tests — whatever it did
    # to them is discarded, and only its changes to the source count.
    touched = sorted({
        line.split("/", 1)[1].strip()
        for line in truth["test_patch"].splitlines()
        if line.startswith(("--- a/", "+++ b/")) and "/dev/null" not in line
    })
    tampered = []
    for name in touched:
        changed = _run(["git", "diff", "--name-only", "--", name], repo)
        if changed.stdout.strip():
            tampered.append(name)
        restored = _run(["git", "checkout", truth["base_commit"], "--", name], repo)
        if restored.returncode != 0:
            # The patch creates this file, so there is nothing to restore — but
            # a previous grading run may have created it, and `git apply` refuses
            # to create a file that exists. Removing it is the reset.
            (repo / name).unlink(missing_ok=True)
    applied = _run(["git", "apply", "-v", str(patch)], repo)
    if applied.returncode != 0:
        return {"correct": False, "error": f"test patch did not apply: {applied.stderr[-400:]}"}

    venv = workspace / f".gradevenv-{python_for(commit_date(repo))}"
    if not venv.exists():
        # The interpreter is pinned as well as the packages: these commits are
        # from 2023 and their conftests use APIs that 3.13 deprecates out from
        # under them. This is the last thing that can be pinned without the
        # Docker image the official harness ships.
        _run(["uv", "venv", "--python", python_for(commit_date(repo)), str(venv)], workspace)
    python = venv / "bin" / "python"
    install = _install(repo, python)
    if install:
        return {"correct": False, "error": install}

    def run_tests(names: list[str], *, repair: int = 2) -> tuple[int, int, str]:
        if not names:
            return 0, 0, ""
        result = _run(
            [str(python), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
             f"--rootdir={repo}", *names],
            repo,
        )
        output = (result.stdout or "") + (result.stderr or "")
        # A test dependency the repository never declared — `requests` at a 2022
        # commit imports brotli in its tests and pins it nowhere. Install what
        # the error names, without the era bound, and try once more.
        # `brotli._brotli` is the interesting case: the name is dotted, and what
        # is broken is the C extension inside an already-installed wheel, so the
        # top-level package has to be reinstalled rather than installed.
        missing = re.findall(
            r"ModuleNotFoundError: No module named '([A-Za-z0-9_.]+)'", output
        )
        top = dict.fromkeys(name.split(".")[0] for name in missing)
        if top and repair:
            for name in top:
                _run(["uv", "pip", "install", "--python", str(python), "--reinstall-package",
                      name, name], repo)
            return run_tests(names, repair=repair - 1)
        passed = len(re.findall(r"^\.", result.stdout, re.M)) if result.stdout else 0
        return result.returncode, passed, output[-600:]

    f2p_code, _, f2p_out = run_tests(truth["fail_to_pass"])
    p2p_code, _, p2p_out = run_tests(truth["pass_to_pass"])
    return {
        "correct": f2p_code == 0 and p2p_code == 0,
        # Recorded, not punished: the tests are reset either way, so an agent
        # that edited them gains nothing and the run is still graded.
        "edited_tests": tampered,
        "fail_to_pass_ok": f2p_code == 0,
        "pass_to_pass_ok": p2p_code == 0,
        "fail_to_pass_tail": f2p_out,
        "pass_to_pass_tail": p2p_out,
    }
