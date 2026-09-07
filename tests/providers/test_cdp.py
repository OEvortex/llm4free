"""Tests for the agent-browser-backed CDP client (llm4free.browser_requests.cdp).

These tests mock ``subprocess.run`` so no real browser / Chrome is required.
They verify that the CDPSession / SyncCDPSession wrappers shell out correctly
and parse the JSON output contract of the agent-browser CLI.
"""

import asyncio
import base64
import json
import subprocess
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from llm4free.browser_requests import cdp as cdp_module
from llm4free.browser_requests.cdp import CDPSession, SyncCDPSession, find_agent_browser


def _agent_browser_json(data: Dict[str, Any], success: bool = True) -> str:
    """Build a fake agent-browser ``--json`` stdout payload."""
    return json.dumps({"success": success, "data": data, "error": None})


def _make_run_side_effect(
    *,
    eval_result: Any = None,
    cookies: List[Dict[str, Any]] = None,
    title: str = "Example",
) -> List[Dict[str, str]]:
    """Return a list of captured command arg-dicts for assertions.

    The returned list is mutated by the patched subprocess.run so tests can
    inspect exactly which agent-browser commands were issued.
    """
    captured: List[Dict[str, str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured.append({"cmd": cmd})
        # Decide what to return based on the subcommand.
        if "eval" in cmd:
            b64 = cmd[cmd.index("-b") + 1]
            _ = base64.b64decode(b64).decode("utf-8")  # ensure decodable
            return subprocess.CompletedProcess(
                cmd, 0, stdout=_agent_browser_json({"result": eval_result}), stderr=""
            )
        if "cookies" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=_agent_browser_json({"cookies": cookies or []}), stderr=""
            )
        if "get" in cmd and "title" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=title, stderr="")
        # open / wait / click / scroll / close -> plain success
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    return captured, fake_run


class TestFindAgentBrowser(unittest.TestCase):
    def test_missing_binary(self):
        with patch.dict("os.environ", {}, clear=False):
            with patch("shutil.which", return_value=None):
                with self.assertRaises(RuntimeError):
                    find_agent_browser()

    def test_found_on_path(self):
        with patch("shutil.which", return_value="/usr/bin/agent-browser"):
            self.assertEqual(find_agent_browser(), "/usr/bin/agent-browser")


class TestSyncCDPSession(unittest.TestCase):
    def test_evaluate_js_and_cookies(self):
        cookies = [{"name": "cf_clearance", "value": "abc", "domain": ".example.com"}]
        captured, fake_run = _make_run_side_effect(
            eval_result="Mozilla/5.0", cookies=cookies
        )
        with patch.object(cdp_module.subprocess, "run", fake_run):
            sess = SyncCDPSession(headless=False)
            sess.start_chrome()
            ua = sess.evaluate_js("navigator.userAgent")
            cookie_dict = sess.get_cookies()
            self.assertEqual(ua, "Mozilla/5.0")
            self.assertEqual(cookie_dict, {"cf_clearance": "abc"})
            sess.close()
        # open + close commands must have been issued.
        joined = " ".join(" ".join(c["cmd"]) for c in captured)
        self.assertIn("open", joined)
        self.assertIn("close", joined)
        self.assertIn("eval", joined)

    def test_navigate_issues_open(self):
        captured, fake_run = _make_run_side_effect(eval_result="")
        with patch.object(cdp_module.subprocess, "run", fake_run):
            sess = SyncCDPSession()
            sess.navigate("https://example.com")
        self.assertTrue(
            any("open" in c["cmd"] and "https://example.com" in c["cmd"] for c in captured)
        )


class TestAsyncCDPSession(unittest.TestCase):
    def test_evaluate_js_async(self):
        captured, fake_run = _make_run_side_effect(eval_result=42)
        with patch.object(cdp_module.subprocess, "run", fake_run):
            sess = CDPSession()
            result = asyncio.run(sess.evaluate_js("1 + 41"))
            self.assertEqual(result, 42)
            asyncio.run(sess.close())

    def test_get_cookies_async(self):
        cookies = [{"name": "a", "value": "1"}, {"name": "b", "value": "2"}]
        captured, fake_run = _make_run_side_effect(cookies=cookies)
        with patch.object(cdp_module.subprocess, "run", fake_run):
            sess = CDPSession()
            cookie_dict = asyncio.run(sess.get_cookies())
            self.assertEqual(cookie_dict, {"a": "1", "b": "2"})
            asyncio.run(sess.close())

    def test_install_console_capture_and_poll(self):
        # First eval installs the capture buffer (returns nothing important);
        # subsequent polls read the buffer which we simulate returning a token.
        side = []

        def fake_run(cmd, *args, **kwargs):
            side.append(cmd)
            if "eval" in cmd:
                b64 = cmd[cmd.index("-b") + 1]
                expr = base64.b64decode(b64).decode("utf-8")
                if "__llm4free_console" in expr:  # poll read
                    return subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=_agent_browser_json(
                            {"result": "CF_CHUNK: hello"}
                        ),
                        stderr="",
                    )
                if "console" in expr:  # install_console_capture
                    return subprocess.CompletedProcess(
                        cmd, 0, stdout=_agent_browser_json({"result": None}), stderr=""
                    )
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=_agent_browser_json({"result": None}), stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        with patch.object(cdp_module.subprocess, "run", fake_run):
            sess = CDPSession()
            asyncio.run(sess.install_console_capture())
            line = asyncio.run(sess.poll_console("CF_CHUNK:", timeout=2))
            self.assertEqual(line, "CF_CHUNK: hello")
            asyncio.run(sess.close())


if __name__ == "__main__":
    unittest.main()
