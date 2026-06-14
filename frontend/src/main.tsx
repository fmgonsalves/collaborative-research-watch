import React, { FormEvent, useEffect, useMemo, useState } from "react";
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
type SourceDetail = SourceSummary & {
  content_hash?: string | null;
  open_url?: string | null;
  open_path?: string | null;
  comments: CommentRecord[];
  tag_records: TagRecord[];
};
type SyncReport = {
  sources_total: number;
  created: number;
  updated: number;
  changed: number;
  missing: number;
  invalid: number;
  issues: ValidationIssue[];
};

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

  const selectedUserRecord = workspace?.users.find((user) => user.email === selectedUser);
  const allTags = useMemo(() => Array.from(new Set(sources.flatMap((source) => source.human_tags))).sort(), [sources]);

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
      .then((state) => {
        setWorkspace(state);
        if (state.users[0]) setSelectedUser(state.users[0].email);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (workspace?.initialized && workspace.has_users) {
      refreshSources().catch((error) => setMessage(error.message));
    }
  }, [workspace?.initialized, workspace?.has_users, search, typeFilter, statusFilter, tagFilter, sort]);

  useEffect(() => {
    if (selectedSourceId) {
      api<SourceDetail>(`/api/sources/${selectedSourceId}`)
        .then(setDetail)
        .catch(() => setDetail(null));
    }
  }, [selectedSourceId, sources]);

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
    return <WorkspaceGate onSelected={(state) => setWorkspace(state)} message={message} setMessage={setMessage} />;
  }

  if (!workspace.has_users) {
    return (
      <UserBootstrap
        workspacePath={workspace.path || ""}
        onCreated={async () => {
          const state = await api<WorkspaceState>("/api/workspace/status");
          setWorkspace(state);
          if (state.users[0]) setSelectedUser(state.users[0].email);
        }}
      />
    );
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
          runAction={runAction}
        />
        <LinkPanel
          busy={busy}
          onCreated={() => refreshSources()}
          runAction={runAction}
        />
        <ReportPanel report={report} issues={workspace.issues} message={message} />
      </section>

      <section className="main-grid">
        <div className="browse-pane">
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
              <option value="missing">Missing</option>
              <option value="skipped_invalid">Invalid</option>
            </select>
            <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} aria-label="Tag filter">
              <option value="">All tags</option>
              {allTags.map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
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
          busy={busy}
          runAction={runAction}
          onChanged={async () => {
            await refreshSources();
            if (selectedSourceId) setDetail(await api<SourceDetail>(`/api/sources/${selectedSourceId}`));
          }}
        />
      </section>
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

function UploadPanel({ busy, runAction, onUploaded }: { busy: boolean; runAction: (action: () => Promise<void>, success: string) => Promise<void>; onUploaded: () => Promise<void> }) {
  const [files, setFiles] = useState<FileList | null>(null);
  return (
    <form
      className="tool-panel"
      onSubmit={(event) => {
        event.preventDefault();
        runAction(async () => {
          const formData = new FormData();
          Array.from(files ?? []).forEach((file) => formData.append("files", file));
          await api("/api/sources/upload", { method: "POST", body: formData });
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

function LinkPanel({ busy, runAction, onCreated }: { busy: boolean; runAction: (action: () => Promise<void>, success: string) => Promise<void>; onCreated: () => Promise<void> }) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  return (
    <form
      className="tool-panel"
      onSubmit={(event) => {
        event.preventDefault();
        runAction(async () => {
          await api("/api/links", { method: "POST", body: JSON.stringify({ url, title }) });
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

function ReportPanel({ report, issues, message }: { report: SyncReport | null; issues: ValidationIssue[]; message: string }) {
  return (
    <div className="tool-panel">
      <h2>Sync</h2>
      {report ? (
        <div className="report-grid">
          <span>{report.sources_total} sources</span>
          <span>{report.created} created</span>
          <span>{report.changed} changed</span>
          <span>{report.missing} missing</span>
          <span>{report.invalid} invalid</span>
        </div>
      ) : (
        <p className="muted">Ready</p>
      )}
      {message && <p className="message">{message}</p>}
      {[...(report?.issues || []), ...issues].slice(0, 4).map((issue) => (
        <p className="message error" key={`${issue.code}-${issue.path || issue.message}`}>
          {issue.code}: {issue.message}
        </p>
      ))}
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

function DetailPanel({ detail, selectedUser, busy, runAction, onChanged }: { detail: SourceDetail | null; selectedUser?: UserRecord; busy: boolean; runAction: (action: () => Promise<void>, success: string) => Promise<void>; onChanged: () => Promise<void> }) {
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
                  <input value={editingTagValue} onChange={(event) => setEditingTagValue(event.target.value)} />
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
          <input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="Add tag" />
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
