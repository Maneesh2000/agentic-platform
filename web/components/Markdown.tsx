"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Assistant replies on the text surface are markdown by contract
 * (prompts/assistant_text.md). Voice replies are plain text by contract, so
 * this is only used in text mode.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="space-y-3 text-sm leading-relaxed [&_a]:underline [&_a]:underline-offset-2 [&_li]:ml-4 [&_li]:list-disc [&_ol_li]:list-decimal">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const isBlock = /language-/.test(className ?? "");
            return isBlock ? (
              <code
                className="block overflow-x-auto rounded-xl border border-white/10 bg-black/40 p-3 font-mono text-xs"
                {...props}
              >
                {children}
              </code>
            ) : (
              <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[0.85em]" {...props}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => <>{children}</>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-white/15 px-2 py-1 font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="border-b border-white/5 px-2 py-1">{children}</td>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
