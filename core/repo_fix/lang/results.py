"""Shared suite-result parsers (languages §3, L-J0).

One parser per report format; adapters call them from `parse_results`.
All three never raise: malformed input yields `errored=True` (the
pipeline treats that as "no usable result" and drafts, never crashes).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from core.repo_fix.lang.base import SuiteResult


def _errored() -> SuiteResult:
    return SuiteResult(total=0, passed=0, failed=0, failed_ids=[], errored=True)


def parse_junit_xml(text: str) -> SuiteResult:
    """JUnit/Surefire/Gradle XML → counts + `classname.name` failed ids."""
    try:
        root = ET.fromstring(text.strip() or "<x/>")
    except ET.ParseError:
        return _errored()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites and root.tag != "testsuites":
        return _errored()
    tests = failures = errors = skipped = 0
    failed_ids: List[str] = []
    for suite in suites:
        try:
            tests += int(float(suite.get("tests", "0") or 0))
            failures += int(float(suite.get("failures", "0") or 0))
            errors += int(float(suite.get("errors", "0") or 0))
            skipped += int(float(suite.get("skipped", "0") or 0))
        except ValueError:
            return _errored()
        for case in suite.iter("testcase"):
            bad = case.find("failure") is not None or case.find("error") is not None
            if not bad:
                continue
            classname = case.get("classname", "") or ""
            name = case.get("name", "") or ""
            if classname and name:
                failed_ids.append(f"{classname}.{name}")
            elif name:
                failed_ids.append(name)
    failed = failures + errors
    passed = max(0, tests - failed - skipped)
    errored = tests == 0 and failed > 0
    return SuiteResult(
        total=passed + failed,
        passed=passed,
        failed=failed,
        failed_ids=failed_ids,
        errored=errored,
    )


def _jest_counts(body: Dict[str, Any]) -> Dict[str, int]:
    total = body.get("numTotalTests")
    if isinstance(total, int):
        return {
            "total": total,
            "passed": int(body.get("numPassedTests") or 0),
            "failed": int(body.get("numFailedTests") or 0),
        }
    passed = failed = 0  # summary missing: derive from assertions
    for result in body.get("testResults", []) or []:
        for assertion in result.get("assertionResults", []) or []:
            if assertion.get("status") == "failed":
                failed += 1
            elif assertion.get("status") == "passed":
                passed += 1
    return {"total": passed + failed, "passed": passed, "failed": failed}


def parse_jest_json(text: str) -> SuiteResult:
    """Jest (`--json`) and Vitest (`--reporter=json`) → SuiteResult.

    Failed ids are `<file> > <Suite> > <test>` (ancestors collapse when
    absent, e.g. `tests/a.test.ts > adds`). File paths are kept as the
    runner printed them (stable within one run).
    """
    try:
        body = json.loads(text)
    except ValueError:
        return _errored()
    if not isinstance(body, dict):
        return _errored()
    counts = _jest_counts(body)
    failed_ids: List[str] = []
    for result in body.get("testResults", []) or []:
        filename = result.get("name", "") or ""
        for assertion in result.get("assertionResults", []) or []:
            if assertion.get("status") != "failed":
                continue
            ancestors = assertion.get("ancestorTitles", []) or []
            title = assertion.get("title", "") or ""
            chain = " > ".join([*(str(a) for a in ancestors), str(title)])
            failed_ids.append(f"{filename} > {chain}" if filename else chain)
    return SuiteResult(
        total=counts["total"],
        passed=counts["passed"],
        failed=counts["failed"],
        failed_ids=failed_ids,
    )


def parse_go_test_json(text: str) -> SuiteResult:
    """`go test -json` stream → counts + `package.Test` failed ids.

    Only per-test verdicts count (package lines carry no test name).
    A package-level `fail` with zero test failures means the build (or
    setup) broke before tests ran → `errored=True`.
    """
    passed = failed = 0
    failed_ids: List[str] = []
    package_failed = False
    saw_json = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue  # raw compiler output interleaved with the stream
        if not isinstance(event, dict):
            continue
        saw_json = True
        action = event.get("Action", "")
        test = event.get("Test", "") or ""
        package = event.get("Package", "") or ""
        if test:
            if action == "pass":
                passed += 1
            elif action == "fail":
                failed += 1
                failed_ids.append(f"{package}.{test}" if package else test)
        elif action == "fail":
            package_failed = True
    if not saw_json:
        return _errored()
    return SuiteResult(
        total=passed + failed,
        passed=passed,
        failed=failed,
        failed_ids=failed_ids,
        errored=package_failed and failed == 0,
    )
