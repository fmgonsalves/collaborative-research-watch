from __future__ import annotations

from pathlib import Path

from .csv_store import read_users, write_users
from .models import BootstrapUserRequest, UserRecord, ValidationIssue, WorkspaceState

WORKSPACE_DIRS = [
    "sources",
    "records/sources",
    "records/comments",
    "records/human-tags",
    "records/ai",
]


class WorkspaceManager:
    def __init__(self) -> None:
        self.current_path: Path | None = None

    def select(self, raw_path: str) -> WorkspaceState:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            return WorkspaceState(
                path=str(path),
                issues=[
                    ValidationIssue(
                        code="workspace_path_not_absolute",
                        message="Workspace path must be absolute.",
                        path=str(path),
                    )
                ],
            )
        path.mkdir(parents=True, exist_ok=True)
        for relative in WORKSPACE_DIRS:
            (path / relative).mkdir(parents=True, exist_ok=True)
        links_csv = path / "links.csv"
        if not links_csv.exists():
            links_csv.write_text("url,title\n", encoding="utf-8")
        self.current_path = path
        return self.status()

    def require(self) -> Path:
        if self.current_path is None:
            raise RuntimeError("Workspace has not been selected.")
        return self.current_path

    def status(self) -> WorkspaceState:
        if self.current_path is None:
            return WorkspaceState()
        users, issues = read_users(self.current_path / "users.csv")
        return WorkspaceState(
            path=str(self.current_path),
            initialized=True,
            has_users=bool(users),
            users=users,
            issues=issues,
        )

    def bootstrap_user(self, request: BootstrapUserRequest) -> UserRecord:
        path = self.require() / "users.csv"
        if path.exists():
            users, _ = read_users(path)
            if users:
                raise ValueError("users.csv already exists with users.")
        user = UserRecord(name=request.name.strip(), email=request.email.strip().lower())
        if not user.name or not user.email:
            raise ValueError("Name and email are required.")
        write_users(path, [user])
        return user
