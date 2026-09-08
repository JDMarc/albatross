"""Read-only updater diagnostics with isolated Git fixtures; never fetch or install."""
import sys
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from albatross_pi import updater
from albatross_pi.state.snapshot import StateSnapshot


def check():
    with tempfile.TemporaryDirectory(prefix="albatross_update_test_") as temporary:
        folder = Path(temporary)
        install = folder / "zip-install"
        install.mkdir()
        with patch.object(updater, "REPO_ROOT", install), patch.object(updater, "_fetch_repository_head") as fetch:
            assert updater.diagnose_repository_install().status == "ZIP/COPY INSTALL"
            assert updater.install_update_from_repository(StateSnapshot()).status == "ZIP/COPY INSTALL"
            fetch.assert_not_called()
            assert not (install / ".git").exists()
        repo = folder / "clone"
        repo.mkdir()

        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

        git("init", "--quiet")
        with patch.object(updater, "REPO_ROOT", repo):
            assert updater.diagnose_repository_install().status == "GIT HEAD INVALID"
            git("-c", "user.name=Updater Test", "-c", "user.email=test@example.invalid",
                "commit", "--quiet", "--allow-empty", "-m", "fixture")
            assert updater.diagnose_repository_install().status == "NO UPDATE REMOTE"
            git("remote", "add", "origin", "https://example.invalid/albatross.git")
            before = git("status", "--porcelain").stdout
            assert updater.diagnose_repository_install().status == "GIT READY"
            assert git("status", "--porcelain").stdout == before
        nested = repo / "copied-hud"
        nested.mkdir()
        with patch.object(updater, "REPO_ROOT", nested):
            assert updater.diagnose_repository_install().status == "WRONG GIT ROOT"
        # Worktrees use a .git FILE, not a directory.
        linked = folder / "linked"
        git("worktree", "add", "--quiet", "--detach", str(linked))
        with patch.object(updater, "REPO_ROOT", linked):
            assert (linked / ".git").is_file()
            assert updater.diagnose_repository_install().status == "GIT READY"

    for error, expected in (
        (FileNotFoundError(), "GIT NOT INSTALLED"),
        (PermissionError(), "GIT ACCESS DENIED"),
        (subprocess.TimeoutExpired("git", 120), "GIT TIMEOUT"),
    ):
        with patch.object(updater, "_run_git", side_effect=error):
            assert updater.diagnose_repository_install().status == expected
    for stderr, expected in (
        ("fatal: detected dubious ownership in repository", "GIT OWNERSHIP"),
        ("fatal: permission denied", "GIT ACCESS DENIED"),
        ("fatal: invalid gitfile format", "GIT METADATA ERROR"),
    ):
        with patch.object(updater, "_run_git", return_value=Mock(returncode=128, stderr=stderr)):
            assert updater.diagnose_repository_install().status == expected
    print("PASS updater: ZIP, missing Git, ownership, access, broken HEAD, remote, parent repo, worktree; no fetch/install")


if __name__ == "__main__":
    check()
