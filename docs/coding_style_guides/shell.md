# Google Shell Style Guide: key rules

The main rules of the
[Google Shell Style Guide](https://google.github.io/styleguide/shellguide.html),
condensed. Each rule links to its section of the full guide. Follow the link
when you need the reasoning, the examples, or a case this page leaves out.

Where this repo's tooling disagrees with the guide, the tooling wins.

> Condensed from [google/styleguide](https://github.com/google/styleguide/tree/a9c5f82)
> at commit `a9c5f82` (2026-11-13). The guide is licensed under
> [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). This page shortens
> and rewords its rules and leaves out the examples.

## When and how to use shell

- **[Which shell](https://google.github.io/styleguide/shellguide.html#s1.1-which-shell-to-use):**
  Bash only. Executables start with `#!/bin/bash` and minimal flags. Set
  options with `set`, so that `bash script_name` behaves the same way.
- **[When to use shell](https://google.github.io/styleguide/shellguide.html#s1.2-when-to-use-shell):**
  Only for small utilities and wrappers that mostly call other programs. If a
  script passes about 100 lines, has complex control flow, or performance
  matters, rewrite it in a structured language now.
- **[File extensions](https://google.github.io/styleguide/shellguide.html#s2.1-file-extensions):**
  Executables have `.sh` or no extension. Libraries must use `.sh` and should
  not be executable.
- **[SUID/SGID](https://google.github.io/styleguide/shellguide.html#s2.2-suid-sgid):**
  Forbidden on shell scripts.
- **[STDOUT vs STDERR](https://google.github.io/styleguide/shellguide.html#s3.1-stdout-vs-stderr):**
  All error messages go to `STDERR`.

## Comments

- **[File header](https://google.github.io/styleguide/shellguide.html#s4.1-file-header):**
  Every file starts with a comment that gives a short overview of its
  contents.
- **[Function comments](https://google.github.io/styleguide/shellguide.html#s4.2-function-comments):**
  Required for any function that is not both obvious and short, and for every
  library function. Describe it, then list `Globals:`, `Arguments:`,
  `Outputs:` and `Returns:` where they apply.
- **[Implementation comments](https://google.github.io/styleguide/shellguide.html#s4.3-implementation-comments):**
  Comment the tricky or unusual parts, not everything.
- **[TODO comments](https://google.github.io/styleguide/shellguide.html#s4.4-todo-comments):**
  `# TODO(username): What to do (bug ####)`, naming the person with the best
  context.

## Formatting

- **[Indentation](https://google.github.io/styleguide/shellguide.html#s5.1-indentation):**
  2 spaces, never tabs. The one exception is the body of a `<<-` here-document.
- **[Line length](https://google.github.io/styleguide/shellguide.html#s5.2-line-length-and-long-strings):**
  80 characters. Put longer strings in a here-document or use an embedded
  newline.
- **[Pipelines](https://google.github.io/styleguide/shellguide.html#s5.3-pipelines):**
  One line if the whole pipeline fits. Otherwise one segment per line, with
  the `|` at the start of the next line, indented 2 spaces.
- **[Control flow](https://google.github.io/styleguide/shellguide.html#s5.4-control-flow):**
  `; then` and `; do` go on the same line as `if`, `for` and `while`. `else`,
  `fi` and `done` go on their own lines.
- **[case](https://google.github.io/styleguide/shellguide.html#s5.5-case-statement):**
  Indent alternatives 2 spaces. A one-line alternative has a space after `)`
  and before `;;`. Split longer alternatives over several lines.
- **[Variable expansion](https://google.github.io/styleguide/shellguide.html#s5.6-variable-expansion):**
  Stay consistent with the file, quote variables, and prefer `"${var}"` to
  `"$var"`.
- **[Quoting](https://google.github.io/styleguide/shellguide.html#s5.7-quoting):**
  Always quote strings that contain variables, command substitutions, spaces
  or shell metacharacters. Use arrays for lists, such as command flags.

## Features and bugs

- **[ShellCheck](https://google.github.io/styleguide/shellguide.html#s6.1-shellcheck):**
  Run it on every script.
- **[Command substitution](https://google.github.io/styleguide/shellguide.html#s6.2-command-substitution):**
  `$(command)`, never backticks.
- **[Tests](https://google.github.io/styleguide/shellguide.html#s6.3-tests):**
  Use `[[ … ]]`, not `[ … ]` or `test`.
- **[Testing strings](https://google.github.io/styleguide/shellguide.html#s6.4-testing-strings):**
  Use `-z` and `-n` for empty and non-empty strings, not filler characters.
- **[Wildcards](https://google.github.io/styleguide/shellguide.html#s6.5-wildcard-expansion-of-filenames):**
  Expand `./*`, not `*`, since a filename can start with `-`.
- **[eval](https://google.github.io/styleguide/shellguide.html#s6.6-eval):**
  Avoid it.
- **[Arrays](https://google.github.io/styleguide/shellguide.html#s6.7-arrays):**
  Store lists, especially argument lists, in arrays and expand them as
  `"${array[@]}"`. If you need more complex data structures, use another
  language.
- **[Pipes to while](https://google.github.io/styleguide/shellguide.html#s6.8-pipes-to-while):**
  Use process substitution or `readarray`, not `cmd | while read`. A pipe
  runs the loop in a subshell, so variables set inside it are lost.
- **[Arithmetic](https://google.github.io/styleguide/shellguide.html#s6.9-arithmetic):**
  `(( … ))` and `$(( … ))`. Never `let`, `$[ … ]` or `expr`. Under `set -e`,
  a standalone `(( … ))` that evaluates to 0 exits the script.
- **[Aliases](https://google.github.io/styleguide/shellguide.html#s6.10-aliases):**
  Do not use them in scripts. Use functions.

## Naming and structure

- **[Function names](https://google.github.io/styleguide/shellguide.html#s7.1-function-names):**
  `lower_case_with_underscores`. Libraries may namespace them as
  `package::function`.
- **[Variable names](https://google.github.io/styleguide/shellguide.html#s7.2-variable-names):**
  Same as function names.
- **[Constants and environment variables](https://google.github.io/styleguide/shellguide.html#s7.3-constants-and-environment-variable-names):**
  `UPPER_CASE`, declared at the top of the file with `readonly` or `export`.
- **[Source filenames](https://google.github.io/styleguide/shellguide.html#s7.4-source-filenames):**
  Lowercase, with underscores if needed: `make_template`, not
  `make-template`.
- **[Local variables](https://google.github.io/styleguide/shellguide.html#s7.5-use-local-variables):**
  Declare function variables with `local`. Declare and assign a command
  substitution on separate lines, since `local` hides the command's exit
  code.
- **[Function location](https://google.github.io/styleguide/shellguide.html#s7.6-function-location):**
  All functions together near the top, below the constants. No executable code
  between functions.
- **[main](https://google.github.io/styleguide/shellguide.html#s7.7-main):**
  A script with at least one other function has a `main` function, placed
  last. The last line calls `main "$@"`.

## Calling commands

- **[Return values](https://google.github.io/styleguide/shellguide.html#s8.1-checking-return-values):**
  Always check them, with `if` or `$?`. For pipelines, use `PIPESTATUS`.
- **[Builtins](https://google.github.io/styleguide/shellguide.html#s8.2-builtin-commands-vs-external-commands):**
  Prefer a Bash builtin, such as parameter expansion, to an external command
  like `sed`.

## Consistency

- **[Be consistent](https://google.github.io/styleguide/shellguide.html#s9-conclusion):**
  Pick one style and use it everywhere.
