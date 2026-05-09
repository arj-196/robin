from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class DockerWrapperTests(unittest.TestCase):
    def run_with_fake_docker(
        self, bin_name: str, args: list[str], env_text: str
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docker_log = tmp_path / "docker.log"
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$DOCKER_LOG"
if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  exit 0
fi
exit 0
""",
                encoding="utf-8",
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)

            home = tmp_path / "home"
            home.mkdir()
            (home / ".codex").mkdir()
            env_file = ROOT / ".env"
            original_env = env_file.read_text(encoding="utf-8")
            env_file.write_text(env_text.format(tmp=tmp), encoding="utf-8")
            try:
                env = {
                    **os.environ,
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                    "DOCKER_LOG": str(docker_log),
                    "HOME": str(home),
                }
                result = subprocess.run(
                    [str(ROOT / "bin" / bin_name), *args],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    env=env,
                    check=False,
                )
            finally:
                env_file.write_text(original_env, encoding="utf-8")

            result.docker_log = docker_log.read_text(encoding="utf-8")  # type: ignore[attr-defined]
            return result

    def test_auto_coder_rewrites_paths_to_container_mounts(self) -> None:
        result = self.run_with_fake_docker(
            "auto-coder",
            ["status"],
            "ROBIN_HOME={tmp}/robin-home\nAUTO_CODER_APPS_ROOT={tmp}/apps\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        log = result.docker_log  # type: ignore[attr-defined]
        self.assertIn("robin-auto-coder python abilities/services/auto-coder/src/main.py status", log)
        self.assertIn("--env ROBIN_HOME=/robin-home", log)
        self.assertIn("--env AUTO_CODER_APPS_ROOT=/apps", log)
        self.assertIn(":/workspace:ro", log)
        self.assertIn(":/robin-home:rw", log)
        self.assertIn(":/apps:rw", log)
        self.assertIn(":/root/.codex:rw", log)
        self.assertNotIn("/var/run/docker.sock", log)

    def test_chores_rewrites_paths_to_container_mounts(self) -> None:
        result = self.run_with_fake_docker(
            "chores",
            ["status"],
            "ROBIN_HOME={tmp}/robin-home\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        log = result.docker_log  # type: ignore[attr-defined]
        self.assertIn("robin-chores python abilities/services/chores/src/main.py status", log)
        self.assertIn("--env ROBIN_HOME=/robin-home", log)
        self.assertIn(":/workspace:ro", log)
        self.assertIn(":/robin-home:rw", log)
        self.assertIn(":/root/.codex:rw", log)
        self.assertNotIn("AUTO_CODER_APPS_ROOT", log)
        self.assertNotIn(":/apps:rw", log)
        self.assertNotIn("/var/run/docker.sock", log)

    def test_history_dashboard_serve_mounts_robin_home_read_only_and_publishes_port(self) -> None:
        result = self.run_with_fake_docker(
            "history-dashboard",
            ["serve"],
            "ROBIN_HOME={tmp}/robin-home\nHISTORY_DASHBOARD_PORT=4242\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        log = result.docker_log  # type: ignore[attr-defined]
        self.assertIn("robin-history-dashboard ./node_modules/.bin/next start --hostname 0.0.0.0 --port 4242", log)
        self.assertIn("--env ROBIN_HOME=/robin-home", log)
        self.assertIn("--publish 4242:4242", log)
        self.assertNotIn("--detach", log)
        self.assertNotIn("--name robin-history-dashboard", log)
        self.assertIn(":/robin-home:ro", log)
        self.assertNotIn("/var/run/docker.sock", log)

    def test_history_dashboard_serve_background_detaches_named_container(self) -> None:
        result = self.run_with_fake_docker(
            "history-dashboard",
            ["serve", "--background"],
            "ROBIN_HOME={tmp}/robin-home\nHISTORY_DASHBOARD_PORT=4242\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "History dashboard is running in the background on http://localhost:4242",
            result.stdout,
        )
        self.assertIn("Stop it with: docker stop robin-history-dashboard", result.stdout)
        log = result.docker_log  # type: ignore[attr-defined]
        self.assertIn("robin-history-dashboard ./node_modules/.bin/next start --hostname 0.0.0.0 --port 4242", log)
        self.assertIn("--publish 4242:4242", log)
        self.assertIn("--detach", log)
        self.assertIn("--name robin-history-dashboard", log)
        self.assertIn(":/robin-home:ro", log)
        self.assertNotIn("/var/run/docker.sock", log)

    def test_history_dashboard_status_mounts_robin_home_read_only_without_publishing_port(self) -> None:
        result = self.run_with_fake_docker(
            "history-dashboard",
            ["status"],
            "ROBIN_HOME={tmp}/robin-home\nHISTORY_DASHBOARD_PORT=4242\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        log = result.docker_log  # type: ignore[attr-defined]
        self.assertIn("robin-history-dashboard node /usr/local/bin/history-dashboard-status.js", log)
        self.assertIn("--env ROBIN_HOME=/robin-home", log)
        self.assertIn(":/robin-home:ro", log)
        self.assertNotIn("--publish", log)
        self.assertNotIn("/var/run/docker.sock", log)


if __name__ == "__main__":
    unittest.main()
