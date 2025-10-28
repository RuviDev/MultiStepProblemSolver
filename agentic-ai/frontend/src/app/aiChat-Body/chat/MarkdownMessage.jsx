// src/app/aiChat-Body/chat/MarkdownMessage.jsx
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const CopyBtn = ({ text }) => {
  const [copied, setCopied] = React.useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {}
      }}
      className="hidden group-hover:flex absolute top-2 right-2 px-2 py-1 text-xs rounded bg-gray-200 dark:bg-[#222]"
      title="Copy code"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
};

const MarkdownMessage = ({ content = "", compact = false }) => {
  const components = {
    p: ({ node, ...props }) => (
      <p className={`${compact ? "" : "mb-2"} whitespace-pre-wrap`} {...props} />
    ),
    a: ({ node, ...props }) => (
      <a
        className="text-blue-600 underline break-words"
        target="_blank"
        rel="noopener noreferrer"
        {...props}
      />
    ),
    img: ({ node, ...props }) => (
      <img className="max-w-full rounded my-2" loading="lazy" {...props} />
    ),
    table: ({ node, ...props }) => (
      <div className="overflow-x-auto my-2">
        <table className="min-w-full text-left text-sm" {...props} />
      </div>
    ),
    th: ({ node, ...props }) => (
      <th className="border-b px-2 py-1 font-semibold" {...props} />
    ),
    td: ({ node, ...props }) => <td className="border-b px-2 py-1" {...props} />,
    code: ({ node, inline, className, children, ...props }) => {
      const text = String(children).replace(/\n$/, "");
      if (inline) {
        return (
          <code
            className="px-1 py-0.5 rounded bg-gray-200 dark:bg-[#222] text-[0.9em]"
            {...props}
          >
            {text}
          </code>
        );
      }
      // Block code
      return (
        <div className="relative group my-2">
          <CopyBtn text={text} />
          <pre className="overflow-x-auto rounded-xl bg-[#f6f8fa] dark:bg-[#111] p-3 text-sm">
            <code {...props}>{text}</code>
          </pre>
        </div>
      );
    },
    // Optional: headings with subtle spacing
    h1: ({ node, ...props }) => <h1 className="text-xl font-semibold mb-2" {...props} />,
    h2: ({ node, ...props }) => <h2 className="text-lg font-semibold mb-2" {...props} />,
    h3: ({ node, ...props }) => <h3 className="text-base font-semibold mb-1" {...props} />,
    ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-2" {...props} />,
    ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-2" {...props} />,
    blockquote: ({ node, ...props }) => (
      <blockquote className="border-l-4 border-gray-300 pl-3 italic my-2" {...props} />
    ),
    hr: () => <hr className="my-3 border-gray-300/70" />,
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={components}
      // SECURITY: we do NOT enable rehypeRaw; HTML tags in content are escaped
    >
      {content || ""}
    </ReactMarkdown>
  );
};

export default MarkdownMessage;
