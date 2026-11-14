import Box from '@mui/material/Box';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

type Props = {
  children: string;
  // Rewrites link targets; the pattern pages turn relative links into repo
  // paths (SPEC §11.2).
  linkHref?: (href: string) => string | null;
};

// Markdown from the tutor or a README, read-only. No raw HTML.
export const Markdown = ({ children, linkHref }: Props) => {
  const components: Components = {
    a: ({ href, children: text }) => {
      const target = href && linkHref ? linkHref(href) : (href ?? null);
      if (target === null) return <code>{text}</code>;
      if (/^https?:/.test(target)) {
        return (
          <a href={target} target="_blank" rel="noreferrer">
            {text}
          </a>
        );
      }
      return (
        <span title={target}>
          {text} (<code>{target}</code>)
        </span>
      );
    },
    // Relative images can't load from the API; show where they are.
    img: ({ src, alt }) => {
      const target =
        typeof src === 'string' && linkHref ? linkHref(src) : (src ?? null);
      if (typeof target === 'string' && /^https?:/.test(target)) {
        return (
          <img src={target} alt={alt ?? ''} style={{ maxWidth: '100%' }} />
        );
      }
      return (
        <span>
          [image: {alt}] (<code>{String(target)}</code>)
        </span>
      );
    },
  };
  return (
    <Box
      sx={{
        '& pre': {
          overflowX: 'auto',
          p: 1.5,
          borderRadius: 1,
          bgcolor: 'action.hover',
        },
        '& code': { fontSize: '0.875em' },
        '& p, & ul, & ol, & pre, & table': { mb: 1.5 },
        '& ul, & ol': { pl: 3 },
        '& h1, & h2, & h3': { mt: 2, mb: 1 },
        '& table': { borderCollapse: 'collapse' },
        '& th, & td': { border: 1, borderColor: 'divider', px: 1 },
      }}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </Box>
  );
};
