import React, { FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type ValidationIssue = { code: string; message: string; path?: string | null };
type UserRecord = { name: string; email: string };
type WorkspaceState = {
  path: string | null;
  initialized: boolean;
  has_users: boolean;
  users: UserRecord[];
  issues: ValidationIssue[];
};
type SourceSummary = {
  source_id: string;
  type: "document" | "link";
  title: string;
  lifecycle_status: string;
  date_added: string;
  updated_at: string;
  relative_path?: string | null;
  original_url?: string | null;
  human_tags: string[];
  comment_count: number;
};
type CommentRecord = {
  comment_id: string;
  source_id: string;
  user_email: string;
  created_at: string;
  updated_at: string;
  body: string;
};
type TagRecord = {
  tag_id: string;
  source_id: string;
  user_email: string;
  tag: string;
  created_at: string;
  updated_at: string;
};
type TagSuggestion = { tag: string; count: number };
type SourceDetail = SourceSummary & {
  open_url?: string | null;
  open_path?: string | null;
  comments: CommentRecord[];
  tag_records: TagRecord[];
};
type SyncSourceEvent = {
  source_id: string;
  title: string;
  type: "document" | "link";
  relative_path?: string | null;
  original_url?: string | null;
};
type SyncReport = {
  sources_total: number;
  created: number;
  updated: number;
  changed: number;
  removed: number;
  removed_comments: number;
  removed_tags: number;
  invalid: number;
  created_sources: SyncSourceEvent[];
  changed_sources: SyncSourceEvent[];
  updated_sources: SyncSourceEvent[];
  removed_sources: SyncSourceEvent[];
  issues: ValidationIssue[];
};

function syncEventTarget(event: SyncSourceEvent): string {
  return event.relative_path || event.original_url || event.title;
}

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(path, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers }
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json();
};

function App() {
  const [workspace, setWorkspace] = useState<WorkspaceState | null>(null);
  const [selectedUser, setSelectedUser] = useState("");
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [detail, setDetail] = useState<SourceDetail | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [sort, setSort] = useState("title");
  const [report, setReport] = useState<SyncReport | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [tagSuggestions, setTagSuggestions] = useState<TagSuggestion[]>([]);

  const selectedUserRecord = workspace?.users.find((user) => user.email === selectedUser);

  const applyWorkspaceState = (state: WorkspaceState) => {
    setWorkspace(state);
  };

  const refreshTagSuggestions = async () => {
    const rows = await api<TagSuggestion[]>("/api/tags");
    setTagSuggestions(rows);
  };

  const refreshSources = async () => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (typeFilter) params.set("type", typeFilter);
    if (statusFilter) params.set("status", statusFilter);
    if (tagFilter) params.set("tag", tagFilter);
    params.set("sort", sort);
    const rows = await api<SourceSummary[]>(`/api/sources?${params.toString()}`);
    setSources(rows);
    if (!selectedSourceId && rows[0]) setSelectedSourceId(rows[0].source_id);
  };

  useEffect(() => {
    api<WorkspaceState>("/api/workspace/status")
      .then(applyWorkspaceState)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (workspace?.initialized && workspace.has_users) {
      refreshSources().catch((error) => setMessage(error.message));
      refreshTagSuggestions().catch(() => undefined);
    }
  }, [workspace?.initialized, workspace?.has_users, search, typeFilter, statusFilter, tagFilter, sort]);

  useEffect(() => {
    if (selectedSourceId) {
      api<SourceDetail>(`/api/sources/${selectedSourceId}`)
        .then(setDetail)
        .catch(() => setDetail(null));
    }
  }, [selectedSourceId]);

  const runAction = async (action: () => Promise<void>, success: string) => {
    setBusy(true);
    setMessage("");
    try {
      await action();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  if (!workspace?.initialized) {
    return <WorkspaceGate onSelected={applyWorkspaceState} message={message} setMessage={setMessage} />;
  }

  if (!workspace.has_users) {
    return (
      <UserBootstrap
        workspacePath={workspace.path || ""}
        onCreated={async () => {
          const state = await api<WorkspaceState>("/api/workspace/status");
          applyWorkspaceState(state);
        }}
      />
    );
  }

  if (!selectedUserRecord) {
    return <UserSelection workspacePath={workspace.path || ""} users={workspace.users} onSelected={setSelectedUser} />;
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>{workspace.path}</h1>
        </div>
        <div className="topbar-actions">
          <select value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)} aria-label="Selected user">
            {workspace.users.map((user) => (
              <option key={user.email} value={user.email}>
                {user.name} ({user.email})
              </option>
            ))}
          </select>
          <button
            disabled={busy}
            onClick={() =>
              runAction(async () => {
                const nextReport = await api<SyncReport>("/api/sync", { method: "POST", body: "{}" });
                setReport(nextReport);
                await refreshSources();
              }, "Workspace resynced.")
            }
          >
            Resync
          </button>
        </div>
      </header>

      <section className="workspace-tools">
        <UploadPanel
          busy={busy}
          onUploaded={() => refreshSources()}
          onReport={setReport}
          runAction={runAction}
        />
        <LinkPanel
          busy={busy}
          onCreated={() => refreshSources()}
          onReport={setReport}
          runAction={runAction}
        />
        <ReportPanel report={report} issues={workspace.issues} message={message} />
      </section>

      <section className="main-grid">
        <div className="browse-pane">
          <h2>Sources</h2>
          <div className="filters">
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search sources, tags, comments" />
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} aria-label="Type filter">
              <option value="">All types</option>
              <option value="document">Documents</option>
              <option value="link">Links</option>
            </select>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Status filter">
              <option value="">All statuses</option>
              <option value="available">Available</option>
              <option value="changed">Changed</option>
            </select>
            <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} aria-label="Tag filter">
              <option value="">All tags</option>
              {tagSuggestions.map((item) => (
                <option key={item.tag} value={item.tag}>
                  {item.tag}
                </option>
              ))}
            </select>
            <select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort">
              <option value="title">Title</option>
              <option value="date_added">Date added</option>
              <option value="status">Status</option>
              <option value="recently_updated">Recently updated</option>
            </select>
          </div>
          <SourceTable sources={sources} selectedSourceId={selectedSourceId} onSelect={setSelectedSourceId} />
        </div>
        <DetailPanel
          detail={detail}
          selectedUser={selectedUserRecord}
          tagSuggestions={tagSuggestions}
          busy={busy}
          runAction={runAction}
          onChanged={async () => {
            await refreshSources();
            await refreshTagSuggestions();
            if (selectedSourceId) setDetail(await api<SourceDetail>(`/api/sources/${selectedSourceId}`));
          }}
        />
      </section>
    </main>
  );
}

function UserSelection({ workspacePath, users, onSelected }: { workspacePath: string; users: UserRecord[]; onSelected: (email: string) => void }) {
  const [email, setEmail] = useState(users[0]?.email || "");
  return (
    <main className="gate">
      <form
        className="gate-panel"
        onSubmit={(event) => {
          event.preventDefault();
          if (email) onSelected(email);
        }}
      >
        <p className="eyebrow">{workspacePath}</p>
        <h1>Select your user</h1>
        <select value={email} onChange={(event) => setEmail(event.target.value)} aria-label="Select your user">
          {users.map((user) => (
            <option key={user.email} value={user.email}>
              {user.name} ({user.email})
            </option>
          ))}
        </select>
        <button disabled={!email}>Continue</button>
      </form>
    </main>
  );
}

function WorkspaceGate({ onSelected, message, setMessage }: { onSelected: (state: WorkspaceState) => void; message: string; setMessage: (value: string) => void }) {
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      onSelected(await api<WorkspaceState>("/api/workspace/select", { method: "POST", body: JSON.stringify({ path }) }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not select workspace.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="gate">
      <form className="gate-panel" onSubmit={submit}>
        <p className="eyebrow">Collaborative Research Watch</p>
        <h1>Select a shared workspace</h1>
        <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="/absolute/path/to/research-watch-root" />
        <button disabled={busy || !path.trim()}>{busy ? "Selecting..." : "Select workspace"}</button>
        {message && <p className="message error">{message}</p>}
      </form>
    </main>
  );
}

function UserBootstrap({ workspacePath, onCreated }: { workspacePath: string; onCreated: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await api<UserRecord>("/api/users/bootstrap", { method: "POST", body: JSON.stringify({ name, email }) });
      await onCreated();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create users.csv.");
    }
  };
  return (
    <main className="gate">
      <form className="gate-panel" onSubmit={submit}>
        <p className="eyebrow">{workspacePath}</p>
        <h1>Create the first user</h1>
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Name" />
        <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="email@example.com" />
        <button disabled={!name.trim() || !email.trim()}>Create users.csv</button>
        {message && <p className="message error">{message}</p>}
      </form>
    </main>
  );
}

function UploadPanel({
  busy,
  runAction,
  onUploaded,
  onReport
}: {
  busy: boolean;
  runAction: (action: () => Promise<void>, success: string) => Promise<void>;
  onUploaded: () => Promise<void>;
  onReport: (report: SyncReport) => void;
}) {
  const [files, setFiles] = useState<FileList | null>(null);
  return (
    <form
      className="tool-panel"
      onSubmit={(event) => {
        event.preventDefault();
        runAction(async () => {
          const formData = new FormData();
          Array.from(files ?? []).forEach((file) => formData.append("files", file));
          const response = await api<{ sync: SyncReport }>("/api/sources/upload", { method: "POST", body: formData });
          onReport(response.sync);
          await onUploaded();
        }, "Upload copied into sources and synced.");
      }}
    >
      <h2>Documents</h2>
      <input type="file" multiple onChange={(event) => setFiles(event.target.files)} />
      <button disabled={busy || !files?.length}>Upload</button>
    </form>
  );
}

function LinkPanel({
  busy,
  runAction,
  onCreated,
  onReport
}: {
  busy: boolean;
  runAction: (action: () => Promise<void>, success: string) => Promise<void>;
  onCreated: () => Promise<void>;
  onReport: (report: SyncReport) => void;
}) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  return (
    <form
      className="tool-panel"
      onSubmit={(event) => {
        event.preventDefault();
        runAction(async () => {
          const response = await api<{ sync: SyncReport }>("/api/links", { method: "POST", body: JSON.stringify({ url, title }) });
          onReport(response.sync);
          setUrl("");
          setTitle("");
          await onCreated();
        }, "Link added and synced.");
      }}
    >
      <h2>Links</h2>
      <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/research" />
      <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Optional title" />
      <button disabled={busy || !url.trim()}>Add link</button>
    </form>
  );
}

function ReportEventList({ title, events }: { title: string; events: SyncSourceEvent[] }) {
  if (!events.length) return null;
  return (
    <div className="report-events">
      <h3>{title}</h3>
      <ul>
        {events.map((event) => (
          <li key={event.source_id}>
            <strong>{event.title}</strong> <span className="muted">{syncEventTarget(event)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReportPanel({ report, issues, message }: { report: SyncReport | null; issues: ValidationIssue[]; message: string }) {
  const allIssues = [...(report?.issues || []), ...issues];
  const visibleIssues = allIssues.slice(0, 4);
  const hiddenIssueCount = Math.max(0, allIssues.length - visibleIssues.length);

  return (
    <div className="tool-panel">
      <h2>Sync</h2>
      {report ? (
        <>
          <div className="report-grid">
            <span>{report.sources_total} sources</span>
            <span>{report.created} created</span>
            <span>{report.changed} changed</span>
            <span>{report.updated} updated</span>
            <span>{report.removed} removed</span>
            <span>{report.invalid} invalid</span>
          </div>
          {(report.removed_comments > 0 || report.removed_tags > 0) && (
            <p className="muted report-cascade">
              Cascade: {report.removed_comments} comment{report.removed_comments === 1 ? "" : "s"},{" "}
              {report.removed_tags} tag{report.removed_tags === 1 ? "" : "s"} removed
            </p>
          )}
          <div className="report-event-lists">
            <ReportEventList title="Created" events={report.created_sources} />
            <ReportEventList title="Changed" events={report.changed_sources} />
            <ReportEventList title="Updated" events={report.updated_sources} />
            <ReportEventList title="Removed" events={report.removed_sources} />
          </div>
        </>
      ) : (
        <p className="muted">Ready</p>
      )}
      {message && <p className="message">{message}</p>}
      {visibleIssues.map((issue) => (
        <div className="issue-message" key={`${issue.code}-${issue.path || issue.message}`}>
          <p className="message error">
            {issue.code}: {issue.message}
          </p>
          {issue.path && <code>{issue.path}</code>}
        </div>
      ))}
      {hiddenIssueCount > 0 && (
        <p className="message error">
          Showing {visibleIssues.length} of {allIssues.length} issues. Fix these and resync to see the next set.
        </p>
      )}
    </div>
  );
}

function SourceTable({ sources, selectedSourceId, onSelect }: { sources: SourceSummary[]; selectedSourceId: string; onSelect: (id: string) => void }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Type</th>
            <th>Status</th>
            <th>Tags</th>
            <th>Comments</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.source_id} className={source.source_id === selectedSourceId ? "selected" : ""} onClick={() => onSelect(source.source_id)}>
              <td>
                <strong>{source.title}</strong>
                <span>{source.original_url || source.relative_path}</span>
              </td>
              <td>{source.type}</td>
              <td><span className={`status ${source.lifecycle_status}`}>{source.lifecycle_status}</span></td>
              <td>{source.human_tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</td>
              <td>{source.comment_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!sources.length && <p className="empty">No sources match the current view.</p>}
    </div>
  );
}

function TagCombobox({
  value,
  onChange,
  suggestions,
  excludeTags,
  placeholder = "Add tag",
  disabled = false,
  id: idProp
}: {
  value: string;
  onChange: (value: string) => void;
  suggestions: TagSuggestion[];
  excludeTags: string[];
  placeholder?: string;
  disabled?: boolean;
  id?: string;
}) {
  const comboId = useId();
  const inputId = idProp || comboId;
  const listboxId = `${inputId}-listbox`;
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);

  const excludeLower = useMemo(() => new Set(excludeTags.map((tag) => tag.toLowerCase())), [excludeTags]);

  const filtered = useMemo(() => {
    const query = value.trim().toLowerCase();
    return suggestions
      .filter((item) => !excludeLower.has(item.tag.toLowerCase()))
      .filter((item) => !query || item.tag.toLowerCase().includes(query))
      .slice(0, 50);
  }, [suggestions, excludeLower, value]);

  useEffect(() => {
    setActiveIndex(-1);
  }, [value, filtered.length]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectSuggestion = (tag: string) => {
    onChange(tag);
    setOpen(false);
    setActiveIndex(-1);
  };

  return (
    <div className="tag-combobox" ref={containerRef}>
      <input
        id={inputId}
        role="combobox"
        aria-expanded={open && filtered.length > 0}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            if (!filtered.length) return;
            event.preventDefault();
            setOpen(true);
            setActiveIndex((index) => (index + 1) % filtered.length);
            return;
          }
          if (event.key === "ArrowUp") {
            if (!filtered.length) return;
            event.preventDefault();
            setOpen(true);
            setActiveIndex((index) => (index <= 0 ? filtered.length - 1 : index - 1));
            return;
          }
          if (event.key === "Enter" && open && activeIndex >= 0) {
            event.preventDefault();
            selectSuggestion(filtered[activeIndex].tag);
            return;
          }
          if (event.key === "Escape") {
            setOpen(false);
            setActiveIndex(-1);
          }
        }}
      />
      {open && filtered.length > 0 && (
        <ul className="tag-combobox-menu" id={listboxId} role="listbox">
          {filtered.map((item, index) => (
            <li
              key={item.tag}
              id={`${listboxId}-option-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              className={index === activeIndex ? "tag-combobox-option tag-combobox-option--active" : "tag-combobox-option"}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => selectSuggestion(item.tag)}
            >
              <span>{item.tag}</span>
              <span className="tag-combobox-count">({item.count})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DetailPanel({
  detail,
  selectedUser,
  tagSuggestions,
  busy,
  runAction,
  onChanged
}: {
  detail: SourceDetail | null;
  selectedUser?: UserRecord;
  tagSuggestions: TagSuggestion[];
  busy: boolean;
  runAction: (action: () => Promise<void>, success: string) => Promise<void>;
  onChanged: () => Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [tag, setTag] = useState("");
  const [editingCommentId, setEditingCommentId] = useState("");
  const [editingCommentBody, setEditingCommentBody] = useState("");
  const [editingTagId, setEditingTagId] = useState("");
  const [editingTagValue, setEditingTagValue] = useState("");
  useEffect(() => {
    setEditingCommentId("");
    setEditingCommentBody("");
    setEditingTagId("");
    setEditingTagValue("");
  }, [detail?.source_id]);
  if (!detail) return <aside className="detail-pane"><p className="empty">Select a source.</p></aside>;
  const userEmail = selectedUser?.email || "";
  return (
    <aside className="detail-pane">
      <div className="detail-head">
        <p className="eyebrow">{detail.type} · {detail.lifecycle_status}</p>
        <h2>{detail.title}</h2>
        {detail.open_url && <a className="open-link" href={detail.open_url} target="_blank" rel="noreferrer">Open link</a>}
        {detail.open_path && <code>{detail.open_path}</code>}
      </div>

      <section>
        <h3>Human-created tags</h3>
        <div className="tag-list">
          {detail.tag_records.map((record) => (
            <div className="editable-row" key={record.tag_id}>
              {editingTagId === record.tag_id ? (
                <>
                  <TagCombobox
                    value={editingTagValue}
                    onChange={setEditingTagValue}
                    suggestions={tagSuggestions}
                    excludeTags={detail.human_tags.filter((item) => item !== record.tag)}
                    disabled={busy}
                  />
                  <button
                    disabled={busy || !editingTagValue.trim() || !userEmail}
                    onClick={() =>
                      runAction(async () => {
                        await api(`/api/tags/${record.tag_id}`, { method: "PUT", body: JSON.stringify({ user_email: userEmail, tag: editingTagValue }) });
                        setEditingTagId("");
                        await onChanged();
                      }, "Tag updated.")
                    }
                  >
                    Save
                  </button>
                </>
              ) : (
                <>
                  <span className="tag">{record.tag}</span>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => {
                      setEditingTagId(record.tag_id);
                      setEditingTagValue(record.tag);
                    }}
                  >
                    Edit
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            runAction(async () => {
              await api(`/api/sources/${detail.source_id}/tags`, { method: "POST", body: JSON.stringify({ user_email: userEmail, tag }) });
              setTag("");
              await onChanged();
            }, "Tag saved.");
          }}
        >
          <TagCombobox
            value={tag}
            onChange={setTag}
            suggestions={tagSuggestions}
            excludeTags={detail.human_tags}
            placeholder="Add tag"
            disabled={busy || !userEmail}
          />
          <button disabled={busy || !tag.trim() || !userEmail}>Add</button>
        </form>
      </section>

      <section>
        <h3>Comments</h3>
        <div className="comments">
          {detail.comments.map((item) => (
            <article key={item.comment_id}>
              {editingCommentId === item.comment_id ? (
                <div className="edit-stack">
                  <textarea value={editingCommentBody} onChange={(event) => setEditingCommentBody(event.target.value)} />
                  <button
                    disabled={busy || !editingCommentBody.trim() || !userEmail}
                    onClick={() =>
                      runAction(async () => {
                        await api(`/api/comments/${item.comment_id}`, { method: "PUT", body: JSON.stringify({ user_email: userEmail, body: editingCommentBody }) });
                        setEditingCommentId("");
                        await onChanged();
                      }, "Comment updated.")
                    }
                  >
                    Save comment
                  </button>
                </div>
              ) : (
                <>
                  <p>{item.body}</p>
                  <div className="comment-meta">
                    <span>{item.user_email} · {new Date(item.updated_at).toLocaleString()}</span>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => {
                        setEditingCommentId(item.comment_id);
                        setEditingCommentBody(item.body);
                      }}
                    >
                      Edit
                    </button>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
        <form
          className="comment-form"
          onSubmit={(event) => {
            event.preventDefault();
            runAction(async () => {
              await api(`/api/sources/${detail.source_id}/comments`, { method: "POST", body: JSON.stringify({ user_email: userEmail, body: comment }) });
              setComment("");
              await onChanged();
            }, "Comment saved.");
          }}
        >
          <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Add a team-visible comment" />
          <button disabled={busy || !comment.trim() || !userEmail}>Add comment</button>
        </form>
      </section>
    </aside>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
