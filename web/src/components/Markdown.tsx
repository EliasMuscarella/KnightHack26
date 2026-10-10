import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Safe markdown renderer for repository documents (EVAL.md). Raw HTML in the source is
 * dropped (`skipHtml`), and react-markdown's default URL transform strips unsafe schemes.
 */
export function Markdown({ source }: { source: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
