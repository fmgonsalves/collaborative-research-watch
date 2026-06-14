from __future__ import annotations

import csv
from pathlib import Path

from .models import UserRecord, ValidationIssue


def read_users(path: Path) -> tuple[list[UserRecord], list[ValidationIssue]]:
    if not path.exists():
        return [], []
    issues: list[ValidationIssue] = []
    users: list[UserRecord] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["name", "email"]:
            return [], [
                ValidationIssue(
                    code="invalid_users_header",
                    message="users.csv must have exactly the columns name,email.",
                    path=str(path),
                )
            ]
        for line_number, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip().lower()
            if not name or not email:
                issues.append(
                    ValidationIssue(
                        code="invalid_user_row",
                        message="User rows require name and email.",
                        path=f"{path}:{line_number}",
                    )
                )
                continue
            if email in seen:
                issues.append(
                    ValidationIssue(
                        code="duplicate_user_email",
                        message=f"Duplicate user email: {email}.",
                        path=f"{path}:{line_number}",
                    )
                )
                continue
            seen.add(email)
            users.append(UserRecord(name=name, email=email))
    return users, issues


def write_users(path: Path, users: list[UserRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "email"])
        writer.writeheader()
        for user in users:
            writer.writerow({"name": user.name, "email": user.email.lower()})


def read_links(path: Path) -> tuple[list[dict[str, str]], list[ValidationIssue]]:
    if not path.exists():
        return [], []
    issues: list[ValidationIssue] = []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["url", "title"]:
            return [], [
                ValidationIssue(
                    code="invalid_links_header",
                    message="links.csv must have exactly the columns url,title.",
                    path=str(path),
                )
            ]
        for line_number, row in enumerate(reader, start=2):
            url = (row.get("url") or "").strip()
            title = (row.get("title") or "").strip()
            if not url:
                issues.append(
                    ValidationIssue(
                        code="invalid_link_row",
                        message="Link rows require url.",
                        path=f"{path}:{line_number}",
                    )
                )
                continue
            rows.append({"url": url, "title": title})
    return rows, issues


def append_link(path: Path, url: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    should_write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["url", "title"])
        if should_write_header:
            writer.writeheader()
        writer.writerow({"url": url, "title": title})
