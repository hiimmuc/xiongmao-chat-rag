import { useEffect, useState } from "react";
import { all, api, json, remove, request } from "../api";
import { ACCEPT, isWorking, uploadDocument } from "../documents";
import { useFileDrop } from "../hooks/useFileDrop";
import type { Doc } from "../types";
import DeletionNotice, { type Receipt } from "./DeletionNotice";
import { Icon, PATH } from "./Icon";
import RowMenu from "./RowMenu";

const STATUS: Record<string, string> = {
  uploading: "Uploading",
  queued: "Waiting",
  processing: "Indexing",
  ready: "Ready",
  failed: "Failed",
};

const size = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

/** A project's documents: drop or browse to upload, then status, rename, download, retry and delete. */
export default function ProjectDocuments({ projectId, onChange }: { projectId: string; onChange: () => void }) {
  const [docs, setDocs] = useState<Doc[] | null>(null),
    [error, setError] = useState(""),
    [uploading, setUploading] = useState(""),
    [receipt, setReceipt] = useState<Receipt>();
  const load = () =>
    all<Doc>(`/documents?project_id=${projectId}`)
      .then(setDocs)
      .catch((e) => setError(e.message));
  const working = (docs ?? []).some(isWorking);

  useEffect(() => {
    setDocs(null);
    setError("");
    setReceipt(undefined);
    void load();
  }, [projectId]);
  useEffect(() => {
    // Check often while files are being indexed (also ones dropped into a chat), rarely otherwise.
    const timer = setInterval(() => void load(), working ? 2500 : 15000);
    return () => clearInterval(timer);
  }, [projectId, working]);

  async function upload(files: File[]) {
    setError("");
    const failed: string[] = [];
    for (const file of files) {
      setUploading(file.name);
      try {
        const doc = await uploadDocument(file, projectId);
        setDocs((d) => [...(d ?? []), doc]);
      } catch (e) {
        failed.push((e as Error).message);
      }
    }
    setUploading("");
    setError(failed.join(" "));
    onChange();
  }
  async function action(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await load();
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function download(d: Doc) {
    const r = await request(`/documents/${d.id}/download`);
    const url = URL.createObjectURL(await r.blob()),
      a = document.createElement("a");
    a.href = url;
    a.download = d.name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const drop = useFileDrop((files) => void upload(files), !uploading);
  const ready = (docs ?? []).filter((d) => d.state === "ready").length;
  return (
    <section className="panel" aria-labelledby="docs-h">
      <div className="panel-head">
        <h2 id="docs-h">Documents</h2>
        {docs && docs.length > 0 && (
          <span className="state">
            {docs.length} total · {ready} ready{working ? " · indexing…" : ""}
          </span>
        )}
      </div>
      <div className="dropzone" data-over={drop.over || undefined} {...drop.props}>
        <Icon d={PATH.file} size={28} />
        <p>
          {uploading ? (
            <span role="status">Uploading {uploading}…</span>
          ) : (
            <>
              <strong>Drag and drop files here</strong> or{" "}
              <label className="browse">
                browse
                <input
                  type="file"
                  accept={ACCEPT}
                  multiple
                  onChange={(e) => {
                    const files = [...(e.target.files ?? [])];
                    if (files.length) void upload(files);
                    e.target.value = "";
                  }}
                />
              </label>
            </>
          )}
        </p>
        <small>Text PDF, TXT or Markdown, up to 10 MiB each. Scanned PDFs need text extraction first.</small>
      </div>
      {error && <p role="alert">{error}</p>}
      {receipt && <DeletionNotice receipt={receipt} />}
      {docs === null && !error && <p className="state" role="status">Loading documents…</p>}
      {docs?.length === 0 && <p className="state">No documents yet. Files you add here, or drop into a chat in this project, appear here.</p>}
      {!!docs?.length && (
        <div className="table-wrap docs-table">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Size</th>
                <th>Status</th>
                <th>Added</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div className="doc-name">
                      <Icon d={PATH.file} size={16} />
                      <span>
                        {d.name}
                        {d.error_code && <small>{d.error_code.replaceAll("_", " ")}</small>}
                      </span>
                    </div>
                  </td>
                  <td className="num">{size(d.bytes)}</td>
                  <td>
                    <span className={"badge badge-" + d.state}>{STATUS[d.state] ?? d.state}</span>
                  </td>
                  <td className="when">{d.created_at ? new Date(d.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : ""}</td>
                  <td className="row-actions">
                    <RowMenu
                      label={`Options for ${d.name}`}
                      items={[
                        { label: "Download", icon: PATH.down, onSelect: () => void action(() => download(d)) },
                        {
                          label: "Rename",
                          icon: PATH.edit,
                          onSelect: () => {
                            const name = prompt("Document name", d.name)?.trim();
                            if (name && name !== d.name) void action(() => api("/documents/" + d.id, json("PATCH", { name })));
                          },
                        },
                        ...(d.state === "failed"
                          ? [{ label: "Retry", icon: PATH.retry, onSelect: () => void action(() => api(`/documents/${d.id}/retry`, { method: "POST" })) }]
                          : []),
                        {
                          label: "Delete",
                          icon: PATH.trash,
                          danger: true,
                          onSelect: () => {
                            if (confirm(`Delete ${d.name}? Chats stop using it at once; cleanup runs in the background.`))
                              void action(async () => setReceipt(await remove("/documents/" + d.id)));
                          },
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
