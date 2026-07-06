import { C } from "../fm/theme.js";

function inlineFormat(text) {
  if (!text) return text;
  const parts = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(<strong key={`b-${m.index}`}>{m[1]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : parts;
}

function normalizeMarkdown(text) {
  return (text || "")
    .replace(/\s+(#{1,3}\s)/g, "\n\n$1")
    .replace(/\s+---\s+/g, "\n\n---\n\n")
    .trim();
}

export default function MarkdownBody({ text, size = "sm" }) {
  const body = normalizeMarkdown(text);
  const lines = body.split("\n");
  const out = [];
  let listItems = null;
  const textSize = size === "xs" ? "text-xs" : "text-sm";

  function flushList() {
    if (listItems?.length) {
      out.push(
        <ul key={`ul-${out.length}`} className={`my-1.5 ml-4 list-disc space-y-0.5 ${textSize}`}>
          {listItems}
        </ul>
      );
      listItems = null;
    }
  }

  lines.forEach((line, i) => {
    const t = line.trim();
    if (!t) return;
    if (t === "---" || t === "***") {
      flushList();
      out.push(<hr key={`hr-${i}`} className="my-2 border-t" style={{ borderColor: C.line }} />);
      return;
    }
    if (t.startsWith("### ")) {
      flushList();
      out.push(
        <h4 key={i} className={`mt-2 mb-0.5 ${textSize} font-semibold`} style={{ color: C.chalk }}>
          {inlineFormat(t.slice(4))}
        </h4>
      );
      return;
    }
    if (t.startsWith("## ")) {
      flushList();
      out.push(
        <h3 key={i} className={`mt-2 mb-0.5 ${textSize} font-semibold`} style={{ color: C.chalk }}>
          {inlineFormat(t.slice(3))}
        </h3>
      );
      return;
    }
    if (t.startsWith("# ")) {
      flushList();
      out.push(
        <h2 key={i} className={`mt-2 mb-0.5 ${textSize} font-bold`} style={{ color: C.chalk }}>
          {inlineFormat(t.slice(2))}
        </h2>
      );
      return;
    }
    if (t.startsWith("- ") || t.startsWith("* ")) {
      if (!listItems) listItems = [];
      listItems.push(
        <li key={i} style={{ color: C.chalk }}>{inlineFormat(t.slice(2))}</li>
      );
      return;
    }
    flushList();
    out.push(
      <p key={i} className={`${textSize} leading-relaxed mb-1`} style={{ color: C.chalk }}>
        {inlineFormat(t)}
      </p>
    );
  });
  flushList();
  return <div>{out}</div>;
}
