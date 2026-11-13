import { useRef, useState, type RefObject } from "react";
import { useDismiss } from "../hooks/useDismiss";
import { providerName } from "../format";
import { ACCEPT } from "../documents";
import type { Doc, Model } from "../types";
import { Icon, PATH } from "./Icon";

const STARTERS = ["Summarize my selected documents", "List the key points with citations", "Explain this in simple terms"];
type Popup = "docs" | "provider" | "model";

type Props = {
  field: RefObject<HTMLTextAreaElement | null>;
  text: string;
  setText: (value: string) => void;
  busy: boolean;
  onSend: () => void;
  onStop: () => void;
  free: boolean;
  docs: Doc[];
  chosen: string[];
  onToggleDoc: (id: string, on: boolean) => void;
  uploading: Doc[];
  onUpload: (files: File[]) => void;
  models: Model[];
  model: string;
  onModel: (id: string) => void;
  showStarters: boolean;
};

/** Message box with document, provider and model pickers and the send or stop button. */
export default function Composer({ field, text, setText, busy, onSend, onStop, free, docs, chosen, uploading, onToggleDoc, onUpload, models, model, onModel, showStarters }: Props) {
  const [popup, setPopup] = useState<Popup>();
  const box = useRef<HTMLDivElement>(null);
  const close = () => {
    setPopup(undefined);
    field.current?.focus();
  };
  useDismiss(!!popup, close, box);

  const current = models.find((m) => m.id === model);
  const providers = [...new Set(models.map((m) => m.provider))];
  const provider = current?.provider || providers[0] || "";
  const ready = docs.filter((d) => d.state === "ready");
  const toggle = (name: Popup) => setPopup(popup === name ? undefined : name);
  const pick = (id: string) => {
    onModel(id);
    close();
  };

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
    >
      <div className="box" ref={box}>
        {(chosen.length > 0 || uploading.length > 0) && (
          <div className="chips">
            {uploading.map((d) => (
              <span className="chip working" key={d.id} title="Reading and indexing; it is switched on for this chat when ready">
                <Icon d={PATH.file} size={14} />
                {d.name}
                <small>processing…</small>
              </span>
            ))}
            {chosen.map((id) => {
              const name = docs.find((d) => d.id === id)?.name || "Document";
              return (
                <span className="chip" key={id}>
                  {name}
                  <button type="button" className="ghost" disabled={busy} aria-label={`Remove ${name}`} onClick={() => onToggleDoc(id, false)}>
                    <Icon d="M6 6l12 12M18 6L6 18" />
                  </button>
                </span>
              );
            })}
          </div>
        )}
        <label className="sr-only" htmlFor="message">
          Message
        </label>
        <textarea
          id="message"
          ref={field}
          rows={1}
          value={text}
          disabled={busy}
          placeholder="Message the assistant…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        <div className="tools">
          <div className="pop-wrap">
            <button
              type="button"
              className="tool"
              disabled={busy}
              aria-haspopup="true"
              aria-expanded={popup === "docs"}
              aria-label={`Attach documents${chosen.length ? `, ${chosen.length} selected` : ""}`}
              onClick={() => toggle("docs")}
            >
              <Icon d={PATH.plus} />
              {chosen.length > 0 && <span className="count">{chosen.length}</span>}
            </button>
            {popup === "docs" && (
              <div className="pop" role="group" aria-label="Answer from these documents">
                <p className="pop-title">{free ? "Documents for this chat" : "Answer from project documents"}</p>
                <label className="upload-btn">
                  {free ? "Upload to this chat" : "Upload to this project"}
                  <input
                    type="file"
                    accept={ACCEPT}
                    multiple
                    onChange={(e) => {
                      const files = [...(e.target.files ?? [])];
                      if (files.length) onUpload(files);
                      e.target.value = "";
                    }}
                  />
                </label>
                {docs
                    .filter((d) => d.state !== "ready")
                    .map((d) => (
                      <p className="state" key={d.id}>
                        {d.name}: {d.state === "failed" ? "could not be processed" : "processing…"}
                      </p>
                    ))}
                {ready.map((d) => (
                  <label className="check" key={d.id}>
                    <input type="checkbox" checked={chosen.includes(d.id)} onChange={(e) => onToggleDoc(d.id, e.target.checked)} />
                    {d.name}
                  </label>
                ))}
                {!ready.length && <p className="state">No ready documents yet. Upload one, or drop files onto the chat.</p>}
              </div>
            )}
          </div>
          <Picker
            name="Provider"
            label={providerName(provider)}
            open={popup === "provider"}
            disabled={busy || !models.length}
            onToggle={() => toggle("provider")}
            options={providers.map((p) => ({ id: p, label: providerName(p) }))}
            selected={provider}
            onSelect={(p) => pick(p === provider ? model : models.find((m) => m.provider === p)!.id)}
          />
          <Picker
            name="Model"
            label={current?.label || model || "Model"}
            open={popup === "model"}
            disabled={busy || !models.length}
            onToggle={() => toggle("model")}
            options={models.filter((m) => m.provider === provider)}
            selected={model}
            onSelect={pick}
          />
          <span className="grow" />
          {busy ? (
            <button type="button" className="send stop" aria-label="Stop response" onClick={onStop}>
              <Icon d="M7 7h10v10H7z" fill />
            </button>
          ) : (
            <button className="send" aria-label="Send" disabled={!text.trim() || !model}>
              <Icon d={PATH.send} />
            </button>
          )}
        </div>
      </div>
      {showStarters && (
        <div className="starters">
          {STARTERS.map((t) => (
            <button
              type="button"
              key={t}
              disabled={busy}
              onClick={() => {
                setText(t);
                field.current?.focus();
              }}
            >
              {t}
            </button>
          ))}
        </div>
      )}
      <p className="fineprint">Enter to send, Shift + Enter for a new line.</p>
    </form>
  );
}

type PickerProps = {
  name: string;
  label: string;
  open: boolean;
  disabled: boolean;
  onToggle: () => void;
  options: { id: string; label: string }[];
  selected: string;
  onSelect: (id: string) => void;
};

function Picker({ name, label, open, disabled, onToggle, options, selected, onSelect }: PickerProps) {
  return (
    <div className="pop-wrap">
      <button type="button" className="tool" disabled={disabled} aria-haspopup="listbox" aria-expanded={open} aria-label={`${name}: ${label}`} onClick={onToggle}>
        {label}
        <Icon d={PATH.chevron} />
      </button>
      {open && (
        <div className="pop" role="listbox" aria-label={name}>
          {options.map((o) => (
            <button type="button" role="option" key={o.id} aria-selected={o.id === selected} className="option" onClick={() => onSelect(o.id)}>
              {o.label}
              {o.id === selected && <Icon d={PATH.check} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
