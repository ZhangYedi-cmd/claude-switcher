"""P0 fail-closed: allowlist, native claude kill, Clash Verge conflict, Shadowrocket self-check."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "claude-switch.sh"
GUARD = ROOT / "daemons" / "claude-bodyguard.sh"


def extract(text, name):
    match = re.search(rf"(?ms)^{name}\(\) \{{\n.*?^\}}", text)
    if not match:
        raise AssertionError(f"missing function {name}")
    return match.group(0)


@unittest.skipUnless(sys.platform == "darwin", "macOS bash/sed semantics")
class AllowlistAndConflictTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.core = CORE.read_text(encoding="utf-8")

    def run_bash(self, script, timeout=8):
        env = dict(os.environ, HOME=str(self.root), PATH=f"{self.root / 'bin'}:/usr/bin:/bin",
                   EXIT_IP_ALLOW_FILE=str(self.root / "exit-ips.allow"))
        return subprocess.run(["/bin/bash", "-c", script], env=env, text=True,
                              capture_output=True, timeout=timeout)

    def test_allowlist_hit_miss_empty_and_comments(self):
        (self.root / "exit-ips.allow").write_text(
            "# note\n  203.0.113.10  \nnot-an-ip\n198.51.100.2\n", encoding="utf-8")
        script = "\n".join([
            'EXIT_ALLOW_FILE="$EXIT_IP_ALLOW_FILE"',
            extract(self.core, "exit_allow_ips"),
            extract(self.core, "exit_allow_status"),
            'exit_allow_status 203.0.113.10',
            'exit_allow_status 198.51.100.9',
            'exit_allow_status ""',
        ])
        run = self.run_bash(script)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("ok:命中", run.stdout)
        self.assertIn("fail:不在白名单", run.stdout)
        self.assertIn("fail:未获取到出口IP", run.stdout)

    def test_allowlist_missing_file_fails_closed(self):
        script = "\n".join([
            'EXIT_ALLOW_FILE="$EXIT_IP_ALLOW_FILE"',
            extract(self.core, "exit_allow_ips"),
            extract(self.core, "exit_allow_status"),
            "exit_allow_status 203.0.113.10",
        ])
        run = self.run_bash(script)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("fail:白名单文件不存在", run.stdout)

    def test_clash_helper_alone_is_not_a_conflict(self):
        bindir = self.root / "bin"
        bindir.mkdir()
        pgrep = bindir / "pgrep"
        pgrep.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$HOME/pgrep-args\"\n"
            "exit 1\n",
            encoding="utf-8")
        pgrep.chmod(0o755)
        script = "\n".join([
            'PROXY_MODE="shadowrocket"',
            'proxy_name() { echo Shadowrocket; }',
            extract(self.core, "clash_verge_conflict"),
            "clash_verge_conflict",
        ])
        run = self.run_bash(script)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("ok:未发现 Clash Verge", run.stdout)
        args = (self.root / "pgrep-args").read_text(encoding="utf-8")
        self.assertNotIn("clash-verge-service", args)

    def test_verge_mihomo_conflicts_with_shadowrocket(self):
        bindir = self.root / "bin"
        bindir.mkdir()
        pgrep = bindir / "pgrep"
        pgrep.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in *erge-mihomo*) exit 0 ;; *) exit 1 ;; esac\n",
            encoding="utf-8")
        pgrep.chmod(0o755)
        script = "\n".join([
            'PROXY_MODE="shadowrocket"',
            'proxy_name() { echo Shadowrocket; }',
            extract(self.core, "clash_verge_conflict"),
            "clash_verge_conflict",
        ])
        run = self.run_bash(script)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("fail:与 Shadowrocket 同时运行", run.stdout)

    def test_shadowrocket_selfcheck_does_not_rewrite_rules(self):
        text = extract(self.core, "shadowrocket_selfcheck")
        self.assertNotIn("defaults write", text)
        self.assertNotIn("osascript", text)
        self.assertIn("不改写规则", text)
        self.assertIn("127.0.0.1:7890", text)


@unittest.skipUnless(sys.platform == "darwin", "macOS bodyguard")
class BodyguardNativeKillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fakebin = self.root / "bin"
        self.fakebin.mkdir()
        (self.root / "Library" / "Logs").mkdir(parents=True)
        guard = GUARD.read_text(encoding="utf-8")
        guard = guard.replace("__HOME__", str(self.root)).replace("__PROXY_MODE__", "shadowrocket")
        self.script = self.root / "bodyguard.sh"
        self.script.write_text(guard, encoding="utf-8")

    def stub(self, name, body):
        path = self.fakebin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def run_guard(self):
        env = dict(os.environ, HOME=str(self.root), CLAUDE_SWITCHER_TEST_ROOT=str(self.root),
                   PATH=f"{self.fakebin}:/usr/bin:/bin")
        return subprocess.run(["/bin/bash", "-c", 'enable -n kill\n. "$1"', "guard", str(self.script)],
                              env=env, capture_output=True, text=True, timeout=5)

    def base_stubs(self, online=False):
        tun = "inet 198.18.0.1" if online else "inet 192.168.1.2"
        self.stub("ifconfig", f"#!/bin/sh\necho '{tun}'\n")
        self.stub("scutil", "#!/bin/sh\necho '(Connected) VPN (com.liguangming.Shadowrocket)'\n")
        self.stub("pgrep", "#!/bin/sh\nexit 1\n")
        self.stub("pkill", "#!/bin/sh\ntouch \"$CLAUDE_SWITCHER_TEST_ROOT/pkill-called\"\n")
        self.stub("id", "#!/bin/sh\necho 4242\n")
        self.stub("kill", "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CLAUDE_SWITCHER_TEST_ROOT/kill-args\"\n")

    def test_truncated_native_and_versioned_binary_are_killed_offline(self):
        self.base_stubs(online=False)
        self.stub("ps", "#!/bin/sh\ncat <<'EOF'\n"
                        "  401  4242 /Users/u /Users/u/.local/bin/claude\n"
                        "  402  4242 /Users/u /Users/u/.local/share/claude/versions/2.1.318\n"
                        "  403  4242 claude-proxy /Users/u/.local/bin/claude-proxy\n"
                        "  404  4242 bash /Users/u/.claude-switcher/claude-bodyguard.sh\n"
                        "EOF\n")
        run = self.run_guard()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        kill_args = (self.root / "kill-args").read_text(encoding="utf-8").strip()
        self.assertEqual(kill_args, "-TERM 401 402")
        log = (self.root / "Library" / "Logs" / "claude-bodyguard.log").read_text(encoding="utf-8")
        self.assertIn("代理离线", log)

    def test_online_but_exit_not_allowlisted_kills_native_claude(self):
        self.base_stubs(online=True)
        allow = self.root / ".config" / "claude-env"
        allow.mkdir(parents=True)
        (allow / "exit-ips.allow").write_text("198.51.100.2\n", encoding="utf-8")
        self.stub("curl", "#!/bin/sh\nprintf '%s\\n' 'ip=203.0.113.10'\n")
        self.stub("ps", "#!/bin/sh\ncat <<'EOF'\n"
                        "  501  4242 /Users/u /Users/u/.local/bin/claude\n"
                        "EOF\n")
        run = self.run_guard()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        kill_args = (self.root / "kill-args").read_text(encoding="utf-8").strip()
        self.assertEqual(kill_args, "-TERM 501")
        log = (self.root / "Library" / "Logs" / "claude-bodyguard.log").read_text(encoding="utf-8")
        self.assertIn("出口不在白名单", log)

    def test_online_allowlisted_exit_does_not_kill(self):
        self.base_stubs(online=True)
        allow = self.root / ".config" / "claude-env"
        allow.mkdir(parents=True)
        (allow / "exit-ips.allow").write_text("# pin\n203.0.113.10\n", encoding="utf-8")
        self.stub("curl", "#!/bin/sh\nprintf '%s\\n' 'ip=203.0.113.10'\n")
        self.stub("ps", "#!/bin/sh\ncat <<'EOF'\n"
                        "  501  4242 /Users/u /Users/u/.local/bin/claude\n"
                        "EOF\n")
        run = self.run_guard()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertFalse((self.root / "kill-args").exists())


if __name__ == "__main__":
    unittest.main()
