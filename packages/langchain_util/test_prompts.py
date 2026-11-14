"""Tests for langchain_util.prompts."""

import tempfile
import unittest
from pathlib import Path

from packages.langchain_util.prompts import (
    PromptPathError,
    load_chat_prompt,
    load_prompt,
    read_template,
    resolve_prompt_path,
)


class PromptFileTestCase(unittest.TestCase):
    """Writes real template files: the loader's whole job is reading them."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path


class ReadTemplateTest(PromptFileTestCase):
    def test_strips_surrounding_whitespace(self) -> None:
        path = self.write("p.jinja", "\nHello {{ name }}\n\n")

        self.assertEqual(read_template(path), "Hello {{ name }}")


class ResolvePromptPathTest(PromptFileTestCase):
    """Choosing a template is as good as writing one, so names must stay put."""

    def test_returns_the_file_inside_root(self) -> None:
        self.write("p.jinja", "hi")

        resolved = resolve_prompt_path("p.jinja", root=self.directory)

        self.assertEqual(resolved, self.directory / "p.jinja")

    def test_allows_a_subdirectory(self) -> None:
        (self.directory / "nested").mkdir()
        self.write("nested/p.jinja", "hi")

        resolved = resolve_prompt_path(Path("nested") / "p.jinja", root=self.directory)

        self.assertEqual(resolved, self.directory / "nested" / "p.jinja")

    def test_rejects_traversal_out_of_root(self) -> None:
        with self.assertRaises(PromptPathError):
            resolve_prompt_path("../escaped.jinja", root=self.directory)

    def test_rejects_traversal_that_returns_inside_root(self) -> None:
        # `a/../../b` leaves the tree even though it ends up looking harmless.
        with self.assertRaises(PromptPathError):
            resolve_prompt_path("nested/../../p.jinja", root=self.directory)

    def test_rejects_an_absolute_path(self) -> None:
        inside = self.write("p.jinja", "hi")

        # Absolute *and* inside root is still refused: the caller picks the
        # directory, so a name that carries its own is a bug or an attack.
        with self.assertRaises(PromptPathError):
            resolve_prompt_path(inside, root=self.directory)

    def test_follows_a_symlink_that_leaves_root(self) -> None:
        outside = Path(self._tmp.name).parent / "outside.jinja"
        outside.write_text("linked", encoding="utf-8")
        self.addCleanup(outside.unlink)
        (self.directory / "link.jinja").symlink_to(outside)

        # Deliberate, and load-bearing: bazel runfiles, ConfigMap mounts, and
        # Nix stores serve every file as a symlink out of the tree, so
        # resolving links would reject real prompts in real deployments.
        # Confinement is about the *name*, which is the attacker-supplied part.
        self.assertEqual(read_template("link.jinja", root=self.directory), "linked")


class ConfinedLoadingTest(PromptFileTestCase):
    def test_read_template_enforces_root(self) -> None:
        self.write("p.jinja", "hello")

        self.assertEqual(read_template("p.jinja", root=self.directory), "hello")
        with self.assertRaises(PromptPathError):
            read_template("../p.jinja", root=self.directory)

    def test_load_prompt_enforces_root(self) -> None:
        self.write("p.jinja", "Hello {{ name }}")

        template = load_prompt("p.jinja", root=self.directory)
        self.assertEqual(template.format(name="jack"), "Hello jack")

        with self.assertRaises(PromptPathError):
            load_prompt("../p.jinja", root=self.directory)

    def test_load_chat_prompt_enforces_root_per_message(self) -> None:
        self.write("system.jinja", "You are terse.")
        self.write("human.jinja", "{{ q }}")

        prompt = load_chat_prompt(
            [("system", "system.jinja"), ("human", "human.jinja")],
            root=self.directory,
        )
        self.assertEqual(sorted(prompt.input_variables), ["q"])

        # One bad path fails the whole prompt, not just its own message.
        with self.assertRaises(PromptPathError):
            load_chat_prompt(
                [("system", "system.jinja"), ("human", "../human.jinja")],
                root=self.directory,
            )

    def test_paths_are_unconstrained_without_a_root(self) -> None:
        path = self.write("p.jinja", "hello")

        # Absolute paths written as literals in source stay the simple case.
        self.assertEqual(read_template(path), "hello")


class LoadPromptTest(PromptFileTestCase):
    def test_derives_input_variables_from_the_file(self) -> None:
        path = self.write("p.jinja", "Summarise {{ topic }} in {{ sentences }}.")

        template = load_prompt(path)

        self.assertEqual(sorted(template.input_variables), ["sentences", "topic"])
        self.assertEqual(
            template.format(topic="bazel", sentences=2),
            "Summarise bazel in 2.",
        )

    def test_partial_variables_are_bound_at_load_time(self) -> None:
        path = self.write("p.jinja", "{{ instructions }}\nQ: {{ q }}")

        template = load_prompt(path, partial_variables={"instructions": "JSON only"})

        self.assertEqual(template.input_variables, ["q"])
        self.assertEqual(template.format(q="why"), "JSON only\nQ: why")

    def test_renders_jinja_control_flow(self) -> None:
        path = self.write(
            "p.jinja",
            "Levels:{% for level in levels %} {{ level }}{% endfor %}"
            "{% if note %}\nNote: {{ note }}{% endif %}",
        )

        template = load_prompt(path)

        self.assertEqual(
            template.format(levels=["low", "high"], note=""),
            "Levels: low high",
        )
        self.assertEqual(
            template.format(levels=[], note="hi"),
            "Levels:\nNote: hi",
        )

    def test_missing_variable_fails_before_the_model_is_called(self) -> None:
        path = self.write("p.jinja", "{{ topic }} / {{ audience }}")

        template = load_prompt(path)

        # jinja2 alone would render an undefined variable as an empty string;
        # LangChain's input validation is what turns the typo into an error.
        with self.assertRaises(KeyError):
            template.invoke({"topic": "bazel"})

    def test_f_string_files_still_load(self) -> None:
        path = self.write("p.txt", "Hello {name}")

        template = load_prompt(path, template_format="f-string")

        self.assertEqual(template.format(name="jack"), "Hello jack")


class LoadChatPromptTest(PromptFileTestCase):
    def test_composes_one_file_per_message(self) -> None:
        system = self.write("system.jinja", "You are {{ persona }}.")
        human = self.write("human.jinja", "Explain {{ topic }}.")

        prompt = load_chat_prompt(
            [("system", system), ("human", human)],
            partial_variables={"persona": "terse"},
        )

        messages = prompt.format_messages(topic="bazel")
        self.assertEqual([m.type for m in messages], ["system", "human"])
        self.assertEqual(messages[0].content, "You are terse.")
        self.assertEqual(messages[1].content, "Explain bazel.")

    def test_input_variables_span_every_file(self) -> None:
        system = self.write("system.jinja", "{{ persona }}")
        human = self.write("human.jinja", "{{ topic }}")

        prompt = load_chat_prompt([("system", system), ("human", human)])

        self.assertEqual(sorted(prompt.input_variables), ["persona", "topic"])


if __name__ == "__main__":
    unittest.main()
