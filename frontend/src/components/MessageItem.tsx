import Markdown from "react-markdown";
import { tokenSummary } from "../format";
import type { Message, Source } from "../types";
import { Icon, PATH } from "./Icon";
import Thinking from "./Thinking";

const FINISHED = ["completed", "failed", "cancelled", "interrupted"];
const FAILED = FINISHED.slice(1);

type Props = {
  message: Message;
  label: string;
  isLatestAnswer: boolean;
  busy: boolean;
  canBranch: boolean;
  copied: boolean;
  onCopy: () => void;
  onRegenerate: () => void;
  onBranch: () => void;
  onSource: (source: Source) => void;
};

/** Group sources by file, keeping their order. */
function byFile(sources: Source[]) {
  const files = new Map<string, Source[]>();
  for (const s of sources) files.set(s.name, [...(files.get(s.name) ?? []), s]);
  return [...files.entries()];
}

/** One chat message; answers also carry copy, regenerate and branch actions, token usage and sources. */
export default function MessageItem({ message: m, label, isLatestAnswer, busy, canBranch, copied, onCopy, onRegenerate, onBranch, onSource }: Props) {
  const answer = m.role === "assistant";
  return (
    <article className={"message " + m.role}>
      {answer && (
        <div className="message-meta">
          <span>{label}</span>
          {FAILED.includes(m.status || "") && <span className="status">{m.status}</span>}
        </div>
      )}
      <div className="bubble">
        {!m.content && m.status === "streaming" && <Thinking />}
        <Markdown
          disallowedElements={["img"]} // no remote images: a rendered URL would leak data when the browser loads it
          components={{
            a: ({ children, ...props }) => (
              <a {...props} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {m.content}
        </Markdown>
      </div>
      {answer && (
        <div className="actions">
          {m.content && (
            <button className="icon-btn" aria-label={copied ? "Copied" : "Copy answer"} title="Copy" onClick={onCopy}>
              <Icon d={copied ? PATH.check : PATH.copy} />
            </button>
          )}
          {m.generation_id && isLatestAnswer && FINISHED.includes(m.status || "") && (
            <button className="icon-btn" disabled={busy} aria-label="Regenerate with current model and documents" title="Regenerate" onClick={onRegenerate}>
              <Icon d={PATH.retry} />
            </button>
          )}
          {canBranch && m.generation_id && m.status === "completed" && (
            <button className="icon-btn" disabled={busy} aria-label="Branch in new chat" title="Branch in new chat" onClick={onBranch}>
              <Icon d={PATH.branch} />
            </button>
          )}
          {m.status === "completed" && m.usage && (
            <span className="usage-line" title="Tokens used by this answer">
              {tokenSummary(m.usage)}
            </span>
          )}
        </div>
      )}
      {answer && !!m.citations?.length && (
        <div className="sources" aria-label="Sources">
          {/* One entry per file; its numbered passages match the [n] markers in the answer. */}
          {byFile(m.citations).map(([name, passages]) => (
            <div key={name} className="source" title={name}>
              <Icon d={PATH.file} size={14} />
              <span className="name">{name}</span>
              {passages.map((s) => (
                <button
                  key={s.id}
                  className="num"
                  aria-label={`Passage ${s.id} from ${name}${s.page ? `, page ${s.page}` : ""}`}
                  title={s.page ? `Page ${s.page}` : `Passage ${s.id}`}
                  onClick={() => onSource(s)}
                >
                  {s.id}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
