from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
RUN_WITH_ENV = ROOT / "bin" / "run-with-env"


class RunWithEnvTests(unittest.TestCase):
    def test_env_path_is_used_for_command_resolution_and_exported_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            fakebin_dir = tmp_path / "fakebin"
            bin_dir.mkdir()
            fakebin_dir.mkdir()

            run_with_env_copy = bin_dir / "run-with-env"
            run_with_env_copy.write_text(RUN_WITH_ENV.read_text(), encoding="utf-8")
            run_with_env_copy.chmod(run_with_env_copy.stat().st_mode | stat.S_IXUSR)

            fake_uv = fakebin_dir / "uv"
            fake_uv.write_text(
                "#!/bin/sh\n"
                "echo FAKE_UV_OK\n",
                encoding="utf-8",
            )
            fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IXUSR)

            env_path = str(fakebin_dir)
            (tmp_path / ".env").write_text(f"PATH={env_path}\n", encoding="utf-8")

            command = "command -v uv; uv; /usr/bin/printenv PATH"
            result = subprocess.run(
                [str(run_with_env_copy), "/bin/bash", "-c", command],
                cwd=tmp_path,
                text=True,
                capture_output=True,
                env={**os.environ, "PATH": "/usr/bin:/bin"},
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(output_lines), 3, result.stdout)
            self.assertEqual(output_lines[0], str(fake_uv))
            self.assertEqual(output_lines[1], "FAKE_UV_OK")
            self.assertEqual(output_lines[-1], env_path)

    def test_missing_env_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            run_with_env_copy = bin_dir / "run-with-env"
            shutil.copy2(RUN_WITH_ENV, run_with_env_copy)
            run_with_env_copy.chmod(run_with_env_copy.stat().st_mode | stat.S_IXUSR)

            result = subprocess.run(
                [str(run_with_env_copy), "echo", "ok"],
                cwd=tmp_path,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing .env file", result.stderr)


if __name__ == "__main__":
    unittest.main()
