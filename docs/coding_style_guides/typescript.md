# Google TypeScript Style Guide: key rules

The main rules of the
[Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html),
condensed. Each rule links to its section of the full guide. Follow the link
when you need the reasoning, the examples, or a case this page leaves out.

Where this repo's tooling disagrees with the guide, the tooling wins. The
TypeScript app in `src/main/typescript/packages/algo-tutor-web` is formatted by
Prettier (`.prettierrc`), linted by ESLint (`eslint.config.js`) and
type-checked with its `tsconfig*.json` files.

> Condensed from [google/styleguide](https://github.com/google/styleguide/tree/a9c5f82)
> at commit `a9c5f82` (2026-11-13). The guide is licensed under
> [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). This page shortens
> and rewords its rules and leaves out the examples.

## Source files

- **[Encoding](https://google.github.io/styleguide/tsguide.html#file-encoding-utf-8):**
  UTF-8. Use the special escape (`\n`), not the numeric one (`\x0a`). Write
  printable non-ASCII characters as themselves.
- **[File structure](https://google.github.io/styleguide/tsguide.html#source-file-structure):**
  In order: copyright, if any; a `@fileoverview` JSDoc, if any; imports; then
  the implementation.
- **[Imports](https://google.github.io/styleguide/tsguide.html#imports):**
  - Use named imports (`import {Foo} from './foo';`) or namespace imports
    (`import * as foo from './foo';`).
  - Default imports only for outside code that requires them. Side-effect
    imports (`import '...';`) only to load a library for its side effects.
  - Use relative paths (`./foo`) inside the same project.
  - [Named or namespace](https://google.github.io/styleguide/tsguide.html#namespace-versus-named-imports):
    named for symbols you use often or that have clear names, namespace for
    many symbols from a large API.
- **[Exports](https://google.github.io/styleguide/tsguide.html#exports):**
  - Named exports only. Never `export default`.
  - Export only what other modules use.
  - No [mutable exports](https://google.github.io/styleguide/tsguide.html#mutable-exports)
    (`export let`).
  - No [container classes](https://google.github.io/styleguide/tsguide.html#container-classes)
    of static members just to group names; export the functions and constants
    themselves.
- **[Import and export type](https://google.github.io/styleguide/tsguide.html#import-export-type):**
  `import type` is allowed for symbols used only as types. Use `export type`
  to re-export a type. Do not write `import()` inside a type annotation.
- **[Modules, not namespaces](https://google.github.io/styleguide/tsguide.html#use-modules-not-namespaces):**
  Never write `namespace Foo {}`, except to work with third-party code.

## Language features

- **[const and let](https://google.github.io/styleguide/tsguide.html#use-const-and-let):**
  `const` by default, `let` only if the variable is reassigned, never `var`.
  [One variable per declaration](https://google.github.io/styleguide/tsguide.html#one-variable-per-declaration).
- **[Arrays](https://google.github.io/styleguide/tsguide.html#array-literals):**
  Never use the `Array()` constructor. Do not add non-numeric properties to an
  array; use a `Map`. Iterate with `for (... of arr)`.
- **[Objects](https://google.github.io/styleguide/tsguide.html#object-literals):**
  - Never use the `Object` constructor.
  - No unfiltered `for (... in ...)`. Use `for (... of Object.keys(...))`.
  - Do not spread class instances or functions.
  - A destructured parameter has one level of unquoted shorthand properties.
- **[Classes](https://google.github.io/styleguide/tsguide.html#classes):**
  - No `;` after a class declaration or between methods. Put a blank line
    between methods.
  - A value used only in the constructor stays a local variable, not a
    member.
  - Always call constructors with parentheses: `new Foo()`.
  - Leave out empty constructors and constructors that only call `super`.
  - Never use `#private` fields; use `private`.
  - [Visibility](https://google.github.io/styleguide/tsguide.html#visibility):
    make everything as private as you can. Never write `public`, except on a
    non-readonly public parameter property.
  - Prefer module-level functions to private static methods.
  - Never change `prototype` directly.
- **[Functions](https://google.github.io/styleguide/tsguide.html#functions):**
  - Prefer `function foo() {}` declarations for named functions. A nested
    function may be either kind; inside a method, prefer an arrow function.
  - No `function` expressions (use arrow functions), except for generators.
  - Use a concise arrow body (`x => x + 1`) only when its value is used.
  - Do not rebind `this`. Use an arrow function, not `.bind(this)`.
  - [Callbacks](https://google.github.io/styleguide/tsguide.html#functions-as-callbacks):
    pass `arr.map(x => f(x))`, not `arr.map(f)`, unless you are sure of both
    signatures.
  - [Arrow function properties](https://google.github.io/styleguide/tsguide.html#arrow-functions-as-properties)
    on classes only for event handlers that must be removed later.
  - Default parameter values have no side effects.
  - Use rest and spread, not `arguments` or `apply`.
  - [Length](https://google.github.io/styleguide/tsguide.html#function-length):
    past about 40 lines, consider splitting.
- **[this](https://google.github.io/styleguide/tsguide.html#features-this):**
  Only in class constructors and methods, in functions that declare a `this`
  type, or in arrow functions defined where `this` is valid.
- **[Strings](https://google.github.io/styleguide/tsguide.html#string-literals):**
  Single quotes. Template literals instead of complex concatenation. No line
  continuations inside a string.
- **[Numbers](https://google.github.io/styleguide/tsguide.html#number-literals):**
  Lowercase prefixes `0x`, `0o` and `0b`. No leading zeros.
- **[Type coercion](https://google.github.io/styleguide/tsguide.html#type-coercion):**
  - `String()`, `Boolean()`, template literals and `!!` are fine.
  - Parse numbers with `Number()` and handle `NaN`. Never use unary `+` or
    `parseFloat`. Use `parseInt` only for a non-decimal radix, after checking
    the input.
  - Compare enum values explicitly; do not convert them to booleans.
- **[Control flow](https://google.github.io/styleguide/tsguide.html#control-flow-statements-blocks):**
  Always use braces, except for an `if` that fits on one line.
- **[Exceptions](https://google.github.io/styleguide/tsguide.html#exception-handling):**
  Throw only `Error` or a subclass, always with `new`. An empty `catch` block
  needs a comment that says why. Keep
  [`try` blocks focused](https://google.github.io/styleguide/tsguide.html#keep-try-blocks-focused).
- **[switch](https://google.github.io/styleguide/tsguide.html#switch-statements):**
  Always have a `default` case, and put it last. A non-empty case never falls
  through.
- **[Equality](https://google.github.io/styleguide/tsguide.html#equality-checks):**
  `===` and `!==`. `== null` is allowed to match both `null` and `undefined`.
- **[Type and non-null assertions](https://google.github.io/styleguide/tsguide.html#type-and-non-nullability-assertions):**
  Avoid `x as Foo` and `y!` without a clear reason; prefer a runtime check. If
  you must assert, use `as`, never `<Foo>x`.
- **[Decorators](https://google.github.io/styleguide/tsguide.html#decorators):**
  Do not define new decorators. Use only the ones a framework provides.
- **[Disallowed features](https://google.github.io/styleguide/tsguide.html#disallowed-features):**
  `new String()`, `new Boolean()` and `new Number()`; leaving out semicolons;
  `const enum`; `debugger`; `with`; `eval` and `Function(string)`; non-standard
  features; changing built-in objects or adding globals.

## Naming

- **[By identifier type](https://google.github.io/styleguide/tsguide.html#naming-rules-by-identifier-type):**
  - `UpperCamelCase`: class, interface, type, enum, decorator, type parameter,
    TSX component.
  - `lowerCamelCase`: variable, parameter, function, method, property, module
    alias.
  - `CONSTANT_CASE`: module-level constants, `static readonly` fields, and enum
    values. A value created more than once, such as a `const` inside a
    function, uses `lowerCamelCase`
    ([Constants](https://google.github.io/styleguide/tsguide.html#identifiers-constants)).
- **[Naming style](https://google.github.io/styleguide/tsguide.html#naming-style):**
  Do not repeat the type in the name. No `_` prefix or suffix for private
  members, no `opt_` prefix, and no `I` prefix on interfaces.
- **[Descriptive names](https://google.github.io/styleguide/tsguide.html#descriptive-names):**
  No unclear abbreviations. Short names only for non-exported names in scope
  for 10 lines or fewer.
- **[Camel case](https://google.github.io/styleguide/tsguide.html#camel-case):**
  Treat acronyms as words: `loadHttpUrl`, not `loadHTTPURL`.
- **[Underscore prefix](https://google.github.io/styleguide/tsguide.html#identifiers-underscore-prefix-suffix):**
  Only for an identifier the syntax requires but the code does not use.
- **[Imports](https://google.github.io/styleguide/tsguide.html#identifiers-imports):**
  Namespace imports are `lowerCamelCase`; file names are `snake_case`.

## Type system

- **[Type inference](https://google.github.io/styleguide/tsguide.html#type-inference):**
  Leave out annotations the compiler infers trivially, such as a string,
  number or boolean literal. Return type annotations are optional.
- **[Undefined and null](https://google.github.io/styleguide/tsguide.html#undefined-and-null):**
  Either may be used, depending on context. A type alias never includes
  `|null` or `|undefined`.
- **[Structural types](https://google.github.io/styleguide/tsguide.html#use-structural-types):**
  Annotate the type where you declare the value: `const foo: Foo = {...}`.
- **[Interfaces](https://google.github.io/styleguide/tsguide.html#prefer-interfaces):**
  Use `interface` for object types, not a `type` alias of an object literal.
- **[Array types](https://google.github.io/styleguide/tsguide.html#arrayt-type):**
  `T[]` and `readonly T[]` for simple types, `Array<T>` for complex ones.
- **[Index signatures](https://google.github.io/styleguide/tsguide.html#indexable-key-string-type):**
  Give the key a meaningful name. Consider `Map` or `Set` instead.
- **[Mapped and conditional types](https://google.github.io/styleguide/tsguide.html#mapped-conditional-types):**
  Use the simplest type construct that works.
- **[any](https://google.github.io/styleguide/tsguide.html#any):** Avoid it. Use
  a specific type or `unknown`. If `any` really is right, as in a test mock,
  suppress the lint warning with a comment that says why.
- **[The `{}` type](https://google.github.io/styleguide/tsguide.html#empty-interface-type):**
  Do not use it. Use `unknown`, `Record<string, T>` or `object`.
- **[Tuples](https://google.github.io/styleguide/tsguide.html#tuple-types):**
  Use a tuple instead of a `Pair` type, but named properties are often
  clearer.
- **[Wrapper types](https://google.github.io/styleguide/tsguide.html#wrapper-types):**
  Never use `String`, `Boolean` or `Number` as types; use `string`, `boolean`
  and `number`. Instead of `Object`, use `object`.
- **[Return-type-only generics](https://google.github.io/styleguide/tsguide.html#return-type-only-generics):**
  Do not create them. When an API has them, give the type argument explicitly.

## Toolchain

- **[Compiler](https://google.github.io/styleguide/tsguide.html#typescript-compiler):**
  All code passes type checking. No `@ts-ignore` or `@ts-nocheck`.
  `@ts-expect-error` only in unit tests, and rarely
  ([details](https://google.github.io/styleguide/tsguide.html#ts-ignore)).

## Comments and documentation

- **[JSDoc versus comments](https://google.github.io/styleguide/tsguide.html#jsdoc-vs-comments):**
  `/** JSDoc */` for documentation that users read; `//` for implementation
  notes. A multi-line comment is several `//` lines, not `/* */`.
- **[Top-level exports](https://google.github.io/styleguide/tsguide.html#document-all-top-level-exports-of-modules):**
  Document every exported symbol. Do not just restate its name.
- **[Methods and functions](https://google.github.io/styleguide/tsguide.html#method-and-function-comments):**
  Start with a third-person verb phrase ("Returns the ..."). Leave out
  descriptions that the name and signature already make obvious.
- **[No JSDoc types](https://google.github.io/styleguide/tsguide.html#jsdoc-type-annotations):**
  No types in `@param` or `@return`. No `@implements`, `@enum`, `@private` or
  `@override` where the code already has the keyword.
- **[Parameter name comments](https://google.github.io/styleguide/tsguide.html#comments-when-calling-a-function):**
  At a call site where a value is unclear:
  `someFunction(/* shouldRender= */ true)`.
- **[JSDoc and decorators](https://google.github.io/styleguide/tsguide.html#place-documentation-prior-to-decorators):**
  Put the JSDoc before the decorator.
- **[Deprecation](https://google.github.io/styleguide/tsguide.html#deprecation):**
  Mark with `@deprecated` and tell callers what to use instead.

## Consistency

- **[Be consistent](https://google.github.io/styleguide/tsguide.html#consistency):**
  When the guide does not settle a choice, match the file, then the directory.
  New files always follow this guide.
