# Google Markdown Style Guide: key rules

The main rules of the
[Google Markdown Style Guide](https://google.github.io/styleguide/docguide/style.html),
condensed. Each rule links to its section of the full guide. Follow the link
when you need the reasoning, the examples, or a case this page leaves out.

Where this repo's tooling disagrees with the guide, the tooling wins. Markdown
is linted with the settings in `.markdownlint.jsonc` at the repo root. For
example, that file allows more than one H1 heading (`MD025` is off), but the
guide asks for one.

> Condensed from [google/styleguide](https://github.com/google/styleguide/tree/a9c5f82)
> at commit `a9c5f82` (2026-11-13). The guide is licensed under
> [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). This page shortens
> and rewords its rules and leaves out the examples.

## Documents

- **[Minimum viable documentation](https://google.github.io/styleguide/docguide/style.html#min_doc):**
  A few fresh, accurate docs beat many stale ones. Keep docs up to date the
  way you keep tests passing, and delete stale content often, in small
  batches.
- **[Better is better than best](https://google.github.io/styleguide/docguide/style.html#better_best):**
  Fast iteration beats a perfect doc. Reviewers approve quickly and suggest
  alternatives. They hold a change back only if it makes the docs worse.
- **[Document layout](https://google.github.io/styleguide/docguide/style.html#layout):**
  1. `# Title`, close to the filename.
  2. A short introduction of 1 to 3 sentences.
  3. A `[TOC]` directive, if the host supports one.
  4. `## Topic` sections, starting at level 2.
  5. `## See also`, with links for further reading.
- **[Table of contents](https://google.github.io/styleguide/docguide/style.html#toc):**
  Add `[TOC]` after the introduction unless the whole page fits on one
  screen.
- **Capitalization:** Use the original capitalization of product, tool and
  binary names.

## Formatting

- **[80-character lines](https://google.github.io/styleguide/docguide/style.html#80):**
  Wrap prose at 80 characters. Links, tables, headings and code blocks are
  [exempt](https://google.github.io/styleguide/docguide/style.html#80_exceptions).
- **[Trailing whitespace](https://google.github.io/styleguide/docguide/style.html#trailing):**
  None. For a hard line break, end the line with a backslash.
- **[Headings](https://google.github.io/styleguide/docguide/style.html#headings):**
  - [ATX style](https://google.github.io/styleguide/docguide/style.html#atx)
    (`## Heading`), not underlined with `===` or `---`.
  - Each heading name is unique and complete, even for subsections, so its
    link anchor is clear.
  - [Spacing](https://google.github.io/styleguide/docguide/style.html#heading_spacing):
    a space after the `#`, and a blank line before and after the heading.
  - [One H1](https://google.github.io/styleguide/docguide/style.html#h1) as
    the title. Every other heading is H2 or deeper.
- **[Lists](https://google.github.io/styleguide/docguide/style.html#lists):**
  Use lazy numbering (`1.` on every item) for long lists that may change, and
  real numbers for short, stable lists.
  [Nested lists](https://google.github.io/styleguide/docguide/style.html#nested_lists)
  are indented 4 spaces, for both numbered and bulleted lists.

## Code

- **[Inline code](https://google.github.io/styleguide/docguide/style.html#inline):**
  Use backticks for short code, field names and generic file types. Also use
  them to
  [escape](https://google.github.io/styleguide/docguide/style.html#code_escape)
  fake paths or URLs that should not become links.
- **[Code blocks](https://google.github.io/styleguide/docguide/style.html#codeblocks):**
  - Use fenced blocks, not
    [indented ones](https://google.github.io/styleguide/docguide/style.html#indented_codeblock).
  - [Declare the language](https://google.github.io/styleguide/docguide/style.html#declare)
    after the opening fence.
  - [Escape newlines](https://google.github.io/styleguide/docguide/style.html#escape_newlines)
    with a trailing `\` in shell commands meant to be copied.
  - [Indent a code block inside a list](https://google.github.io/styleguide/docguide/style.html#nest_codeblock)
    so that it does not break the list.

## Links

- **[Shorten links](https://google.github.io/styleguide/docguide/style.html#links)**
  wherever possible.
- **[Explicit paths](https://google.github.io/styleguide/docguide/style.html#explicitpaths):**
  Link to other Markdown files by path, not by full URL.
- **[Relative paths](https://google.github.io/styleguide/docguide/style.html#relativelinks):**
  Fine within the same directory. Avoid `../` paths.
- **[Link text](https://google.github.io/styleguide/docguide/style.html#link_title):**
  Write the sentence, then link its most fitting phrase. Never use "here",
  "link", or the bare URL as link text.
- **[Reference links](https://google.github.io/styleguide/docguide/style.html#reference_links):**
  Use them for
  [long URLs](https://google.github.io/styleguide/docguide/style.html#reference_links_long)
  or for a
  [URL used many times](https://google.github.io/styleguide/docguide/style.html#reference_links_dedupe).
  [Define each one](https://google.github.io/styleguide/docguide/style.html#reference_links_define)
  at the end of the section where it is first used.

## Images, tables and HTML

- **[Images](https://google.github.io/styleguide/docguide/style.html#images):**
  Use them sparingly; prefer simple screenshots. Always give alt text.
- **[Tables](https://google.github.io/styleguide/docguide/style.html#tables):**
  Only for tabular data that readers scan. If a list works, use a list.
- **[Markdown over HTML](https://google.github.io/styleguide/docguide/style.html#html):**
  Avoid HTML. Standard Markdown covers almost every need except big tables.
