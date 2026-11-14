# Google Python Style Guide: key rules

The main rules of the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html),
condensed. Each rule links to its section of the full guide. Follow the link
when you need the reasoning, the examples, or a case this page leaves out.

Where this repo's tooling disagrees with the guide, the tooling wins. This repo
lints with ruff (not pylint) and type-checks with mypy, both configured in
`pyproject.toml`. For example, `ruff format` wraps lines at 88 columns, not 80.

> Condensed from [google/styleguide](https://github.com/google/styleguide/tree/a9c5f82)
> at commit `a9c5f82` (2026-11-13). The guide is licensed under
> [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). This page shortens
> and rewords its rules and leaves out the examples.

## Language rules

- **[Lint](https://google.github.io/styleguide/pyguide.html#lint):** Run a
  linter. Suppress a warning on its line by name, and say why if the name does
  not make it obvious.
- **[Imports](https://google.github.io/styleguide/pyguide.html#imports):** Use
  `import x` for packages and modules, and `from x import y` when `y` is a
  module. Use `as` only for a name clash, a long or generic name, or a standard
  abbreviation such as `import numpy as np`. Import `typing` and
  `collections.abc` symbols directly.
- **[Packages](https://google.github.io/styleguide/pyguide.html#packages):**
  Import each module by its full package path. Do not use relative imports.
- **[Exceptions](https://google.github.io/styleguide/pyguide.html#exceptions):**
  - Raise built-in exceptions where they fit, such as `ValueError` for a
    violated precondition.
  - Do not use `assert` to validate input or to control logic. In pytest
    tests, `assert` is expected.
  - Custom exceptions inherit from an existing exception class, end in
    `Error`, and do not repeat the module name (not `foo.FooError`).
  - Do not catch everything (`except:` or `except Exception`) unless you
    re-raise, or the code is an isolation point that records and suppresses
    errors.
  - Keep `try` blocks small. Use `finally` for cleanup.
- **[Mutable global state](https://google.github.io/styleguide/pyguide.html#global-variables):**
  Avoid it. If you must have it, prefix the name with `_`, expose it through
  functions, and explain why in a comment. Module-level constants are fine and
  use `ALL_CAPS`.
- **[Nested functions and classes](https://google.github.io/styleguide/pyguide.html#nested-classes-functions):**
  Nest only to close over a local value other than `self` or `cls`. To hide a
  helper, prefix it with `_` at module level instead.
- **[Comprehensions](https://google.github.io/styleguide/pyguide.html#comprehensions):**
  Allowed, but not with more than one `for` clause or filter. Prefer
  readability to brevity.
- **[Default iterators](https://google.github.io/styleguide/pyguide.html#default-iterators-operators):**
  Write `for key in d` and `if x in seq`, not `d.keys()` or index loops. Do
  not change a container while you iterate over it.
- **[Generators](https://google.github.io/styleguide/pyguide.html#generators):**
  Fine. The docstring uses `Yields:` instead of `Returns:`.
- **[Lambdas](https://google.github.io/styleguide/pyguide.html#lambdas):**
  One-liners only. Use the `operator` module instead (`operator.mul`, not
  `lambda x, y: x * y`) when it has the function.
- **[Conditional expressions](https://google.github.io/styleguide/pyguide.html#conditional-expressions):**
  Simple cases only. Each part must fit on one line.
- **[Default arguments](https://google.github.io/styleguide/pyguide.html#default-arguments):**
  Never use a mutable default. Use `None` and set the value in the body.
- **[Properties](https://google.github.io/styleguide/pyguide.html#properties):**
  Use `@property` only for a cheap, derived value or controlled access. A
  property that only reads and writes a private attribute should be a public
  attribute instead.
- **[True/False evaluations](https://google.github.io/styleguide/pyguide.html#truefalse-evaluations):**
  Write `if seq:` and `if not seq:`. Check for `None` with `is None`. Never
  compare a boolean to `False` with `==`. An integer may be compared to `0`
  explicitly. For NumPy arrays, test `.size`.
- **[Decorators](https://google.github.io/styleguide/pyguide.html#decorators):**
  Use them only for a clear gain. A decorator must not depend on files,
  sockets or databases. Do not use `staticmethod`; write a module-level
  function. Use `classmethod` only for named constructors or class-wide state.
- **[Threading](https://google.github.io/styleguide/pyguide.html#threading):**
  Do not rely on built-in types being atomic. Pass data with `queue.Queue`,
  and prefer `threading.Condition` to bare locks.
- **[Power features](https://google.github.io/styleguide/pyguide.html#power-features):**
  Avoid metaclasses, bytecode access, dynamic inheritance, import hacks,
  reflection tricks and custom `__del__`. Standard library code that uses
  them, such as `dataclasses`, `enum` and `abc`, is fine.
- **[Type-annotated code](https://google.github.io/styleguide/pyguide.html#typed-code):**
  Annotate public APIs and run a type checker.

## Style rules

- **[Line length](https://google.github.io/styleguide/pyguide.html#line-length):**
  80 characters. Long imports, URLs in comments, and long constant strings
  without spaces are exempt. Wrap with implicit joining inside brackets, never
  with a backslash.
- **[Parentheses](https://google.github.io/styleguide/pyguide.html#parentheses):**
  Do not put them around `return` values or `if` conditions, except to wrap a
  line or to show a tuple.
- **[Indentation](https://google.github.io/styleguide/pyguide.html#indentation):**
  4 spaces, never tabs. Align wrapped elements vertically, or use a hanging
  4-space indent.
- **[Trailing commas](https://google.github.io/styleguide/pyguide.html#trailing-comma):**
  Add one when the closing bracket is on its own line, and for a one-element
  tuple.
- **[Blank lines](https://google.github.io/styleguide/pyguide.html#blank-lines):**
  Two between top-level definitions, one between methods, none right after a
  `def` line.
- **[Whitespace](https://google.github.io/styleguide/pyguide.html#whitespace):**
  Follow PEP 8. No trailing whitespace. Put spaces around `=` in a parameter
  only when it has both a type annotation and a default.
- **[Shebang](https://google.github.io/styleguide/pyguide.html#shebang-line):**
  Only on a file that runs directly: `#!/usr/bin/env python3`.
- **[Strings](https://google.github.io/styleguide/pyguide.html#strings):** Format
  with f-strings, `%` or `.format()`. Do not build a string with `+` in a
  loop; join a list instead. Use one quote character consistently in a file,
  and `"""` for multi-line strings.
- **[Logging](https://google.github.io/styleguide/pyguide.html#logging):** Pass
  a string literal with `%` placeholders and the values as arguments, never an
  f-string.
- **[Error messages](https://google.github.io/styleguide/pyguide.html#error-messages):**
  The message matches the actual condition, interpolated values are clearly
  marked, and the text is easy to grep.
- **[Files and other resources](https://google.github.io/styleguide/pyguide.html#files):**
  Close files, sockets and connections explicitly. Prefer `with`.
- **[TODO comments](https://google.github.io/styleguide/pyguide.html#todo):**
  `# TODO(link-to-issue): What to do.` The context is a link, ideally a bug,
  not a person or team.
- **[Import formatting](https://google.github.io/styleguide/pyguide.html#imports-formatting):**
  One import per line, except `typing` and `collections.abc` symbols. Put
  imports at the top of the file in groups: `__future__`, standard library,
  third party, then this repo. Within a group, sort by full module path,
  ignoring case.
- **[Statements](https://google.github.io/styleguide/pyguide.html#statements):**
  One per line. `if x: y` on one line only when there is no `else` and it
  fits. Never for `try`/`except`.
- **[Getters and setters](https://google.github.io/styleguide/pyguide.html#getters-and-setters):**
  Only when getting or setting does real work. Otherwise use a public
  attribute.
- **[Naming](https://google.github.io/styleguide/pyguide.html#naming):**
  - `module_name`, `package_name`, `ClassName`, `ExceptionName`,
    `function_name`, `method_name`, `GLOBAL_CONSTANT_NAME`, `global_var_name`,
    `instance_var_name`, `parameter_name`, `local_var_name`.
  - Prefix internal names with `_`. Avoid `__` name mangling.
  - Names are descriptive. No unclear abbreviations, and no type in the name
    (not `id_to_name_dict`).
  - Single letters only for counters (`i`), exceptions (`e`), file handles
    (`f`), private type variables, and notation from a cited paper.
  - Filenames end in `.py` and have no dashes.
- **[Main](https://google.github.io/styleguide/pyguide.html#main):** Put the
  program in `main()` behind `if __name__ == '__main__':`. Importing a module
  must have no side effects.
- **[Function length](https://google.github.io/styleguide/pyguide.html#function-length):**
  No hard limit. Past about 40 lines, consider splitting the function.

## Docstrings and comments

- **[Docstrings](https://google.github.io/styleguide/pyguide.html#docstrings):**
  Always `"""`. The summary is one line of at most 80 characters ending in a
  period, `?` or `!`. Any further text follows a blank line.
- **[Modules](https://google.github.io/styleguide/pyguide.html#module-docs):**
  Start each file with a docstring that describes its contents and usage. Test
  modules and `test_` methods do not need one.
- **[Functions and methods](https://google.github.io/styleguide/pyguide.html#function-docs):**
  - Required for public API, nontrivial size, or non-obvious logic.
  - Describe how to call the function and what it does, not how it works.
  - Descriptive ("Fetches rows.") or imperative ("Fetch rows.") style, the
    same throughout a file.
  - Sections `Args:`, `Returns:` (`Yields:` for generators) and `Raises:`,
    with a hanging indent of 2 or 4 spaces.
  - Leave out `Returns:` when the function returns `None`, or when the
    summary starts with "Returns" and says it all.
  - Do not list exceptions raised only when a caller misuses the API.
  - A method marked `@override` needs no docstring unless it changes the
    contract.
- **[Classes](https://google.github.io/styleguide/pyguide.html#class-docs):**
  The summary says what an instance represents. List public attributes in an
  `Attributes:` section.
- **[Block and inline comments](https://google.github.io/styleguide/pyguide.html#comments):**
  Comment the tricky parts. Explain intent; never restate the code. Put at
  least two spaces between the code and `#`.
- **[Punctuation and grammar](https://google.github.io/styleguide/pyguide.html#punctuation-spelling-grammar):**
  Write comments as readable prose with correct capitalization and
  punctuation.

## Type annotations

- **[General rules](https://google.github.io/styleguide/pyguide.html#typing-general):**
  Annotate at least public APIs. Do not annotate `self`, `cls` or the return
  of `__init__`. Use `Self` when a method returns its own type.
- **[None](https://google.github.io/styleguide/pyguide.html#none-type):** Write
  `X | None` explicitly, never `a: str = None`.
- **[Typing imports](https://google.github.io/styleguide/pyguide.html#typing-imports):**
  Import the symbols themselves, such as `from collections.abc import Sequence`.
  For parameters, prefer abstract types like `Sequence` to `list`. Use
  built-in generics (`list[int]`, `tuple[int, str]`), not `typing.List`.
- **[Generics](https://google.github.io/styleguide/pyguide.html#generics):**
  Always give type parameters. If the parameter really is `Any`, write `Any`.
- **[Ignoring types](https://google.github.io/styleguide/pyguide.html#typing-ignore):**
  Disable checking on one line with `# type: ignore`.

## Consistency

- **[Be consistent](https://google.github.io/styleguide/pyguide.html#consistency):**
  When the guide does not settle a choice, match the code around you.
