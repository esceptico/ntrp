import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ gfm: true, breaks: true });

const COPY_ICON_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';

/** Wrap each `<pre><code class="language-XXX">...</code></pre>` block in a
 *  custom container that exposes the language label and a copy button. The
 *  resulting `<button.code-block-copy>` is wired up at the React layer via
 *  click delegation in `<MarkdownContent>`. */
function wrapCodeBlocks(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  for (const pre of Array.from(doc.body.querySelectorAll("pre"))) {
    const code = pre.querySelector("code");
    if (!code) continue;
    const lang = code.className.match(/language-(\S+)/)?.[1] ?? "";
    const text = code.textContent ?? "";

    const wrapper = doc.createElement("div");
    wrapper.className = "code-block";

    const header = doc.createElement("div");
    header.className = "code-block-header";

    const langSpan = doc.createElement("span");
    langSpan.className = "code-block-lang";
    langSpan.textContent = lang;
    header.appendChild(langSpan);

    const button = doc.createElement("button");
    button.type = "button";
    button.className = "code-block-copy";
    button.setAttribute("aria-label", "Copy code");
    button.setAttribute("data-code", encodeURIComponent(text));
    button.innerHTML = COPY_ICON_SVG;
    header.appendChild(button);

    wrapper.appendChild(header);
    pre.parentNode?.insertBefore(wrapper, pre);
    wrapper.appendChild(pre);
  }
  return doc.body.innerHTML;
}

export function renderMarkdown(content: string): string {
  if (!content) return "";
  const html = marked.parse(content, { async: false }) as string;
  const sanitized = DOMPurify.sanitize(html, {
    ADD_ATTR: ["target", "rel"],
    FORBID_TAGS: ["style", "iframe", "form", "input", "button"],
  });
  // wrapCodeBlocks adds our own controlled buttons after sanitization, so
  // user-supplied markdown still can't inject one.
  return wrapCodeBlocks(sanitized);
}

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, char => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}
