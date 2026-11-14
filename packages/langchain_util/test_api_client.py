"""Tests for langchain_util.api_client."""

import os
import unittest
from unittest.mock import patch

from packages.langchain_util import api_client
from packages.langchain_util.api_client import (
    get_embeddings_client,
    get_langchain_client,
)

AZURE_ENV = {
    "AZURE_OPENAI_API_KEY": "azure-key",
    "AZURE_OPENAI_DEPLOYMENT_NAME": "my-deployment",
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
    "OPENAI_API_VERSION": "2024-02-01",
}


class AzureClientTest(unittest.TestCase):
    def test_deployment_name_reaches_the_real_field(self) -> None:
        with patch.dict("os.environ", AZURE_ENV, clear=True):
            client = get_langchain_client("azure")

        # Passing AZURE_OPENAI_DEPLOYMENT_NAME= as a kwarg made pydantic shunt
        # it into model_kwargs, where it became an API request-body parameter
        # and the deployment itself was never set.
        self.assertEqual(client.deployment_name, "my-deployment")
        self.assertEqual(client.model_kwargs, {})

    def test_explicit_deployment_kwarg_wins(self) -> None:
        with patch.dict("os.environ", AZURE_ENV, clear=True):
            client = get_langchain_client("azure", azure_deployment="override")

        self.assertEqual(client.deployment_name, "override")

    def test_missing_env_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            get_langchain_client("azure")

    def test_passes_extra_kwargs_through(self) -> None:
        with patch.dict("os.environ", AZURE_ENV, clear=True):
            client = get_langchain_client("azure", temperature=0.2)

        self.assertEqual(client.temperature, 0.2)
        self.assertTrue(client.verbose)


class OpenAIClientTest(unittest.TestCase):
    def test_alias_env_vars_are_applied(self) -> None:
        env = {
            "LLM_ZSH_PYTHON_OPENAI_API_KEY": "aliased-key",
            "LLM_ZSH_PYTHON_OPENAI_MODEL": "aliased-model",
        }
        with patch.dict("os.environ", env, clear=True):
            client = get_langchain_client("openai")

            self.assertEqual(client.model_name, "aliased-model")

    def test_absent_alias_does_not_clobber_direct_env(self) -> None:
        env = {"OPENAI_API_KEY": "direct-key", "OPENAI_MODEL": "direct-model"}
        with patch.dict("os.environ", env, clear=True):
            client = get_langchain_client("openai")

            # Writing os.environ unconditionally replaced a valid
            # OPENAI_API_KEY with "" whenever the alias was unset.
            import os

            self.assertEqual(os.environ["OPENAI_API_KEY"], "direct-key")
            self.assertEqual(client.model_name, "direct-model")

    def test_alias_takes_precedence_when_both_set(self) -> None:
        env = {
            "OPENAI_API_KEY": "direct-key",
            "OPENAI_MODEL": "direct-model",
            "LLM_ZSH_PYTHON_OPENAI_MODEL": "aliased-model",
        }
        with patch.dict("os.environ", env, clear=True):
            client = get_langchain_client("openai")

            self.assertEqual(client.model_name, "aliased-model")

    def test_missing_env_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            get_langchain_client("openai")


class OllamaClientTest(unittest.TestCase):
    def test_model_comes_from_env(self) -> None:
        with patch.dict("os.environ", {"OLLAMA_MODEL": "llama3"}, clear=True):
            client = get_langchain_client("ollama")

        self.assertEqual(client.model, "llama3")

    def test_missing_env_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            get_langchain_client("ollama")

    def test_explicit_model_needs_no_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            client = get_langchain_client("ollama", model="qwen3.6:35b")

        self.assertEqual(client.model, "qwen3.6:35b")

    def test_explicit_model_wins_over_env(self) -> None:
        with patch.dict("os.environ", {"OLLAMA_MODEL": "llama3"}, clear=True):
            client = get_langchain_client("ollama", model="qwen3.6:35b")

        self.assertEqual(client.model, "qwen3.6:35b")


class EmbeddingsClientTest(unittest.TestCase):
    def test_openai_model_is_the_embedding_one(self) -> None:
        env = {
            "OPENAI_API_KEY": "key",
            "OPENAI_MODEL": "gpt-chat",
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
        }
        with patch.dict("os.environ", env, clear=True):
            client = get_embeddings_client("openai")

        self.assertEqual(client.model, "text-embedding-3-small")

    def test_openai_key_alias_is_applied(self) -> None:
        env = {
            "LLM_ZSH_PYTHON_OPENAI_API_KEY": "aliased-key",
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
        }
        with patch.dict("os.environ", env, clear=True):
            get_embeddings_client("openai")

    def test_openai_without_embedding_model_raises(self) -> None:
        env = {"OPENAI_API_KEY": "key", "OPENAI_MODEL": "gpt-chat"}
        with patch.dict("os.environ", env, clear=True), self.assertRaises(ValueError):
            get_embeddings_client("openai")

    def test_azure_deployment_reaches_the_real_field(self) -> None:
        env = AZURE_ENV | {"AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "embed-deployment"}
        with patch.dict("os.environ", env, clear=True):
            client = get_embeddings_client("azure")

        self.assertEqual(client.deployment, "embed-deployment")

    def test_ollama_model_comes_from_env(self) -> None:
        env = {"OLLAMA_EMBEDDING_MODEL": "nomic-embed-text"}
        with patch.dict("os.environ", env, clear=True):
            client = get_embeddings_client("ollama")

        self.assertEqual(client.model, "nomic-embed-text")


class RequireEnvVarsTest(unittest.TestCase):
    def test_check_environ_openai_raises_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                api_client.check_environ_openai()
            self.assertIn("OPENAI_API_KEY", str(ctx.exception))
            self.assertIn("OPENAI_MODEL", str(ctx.exception))

    def test_check_environ_openai_passes_when_set(self) -> None:
        env = {"OPENAI_API_KEY": "key", "OPENAI_MODEL": "gpt-test"}
        with patch.dict(os.environ, env, clear=True):
            api_client.check_environ_openai()

    def test_check_environ_ollama_raises_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                api_client.check_environ_ollama()

    def test_check_environ_azure_openai_raises_when_partially_set(self) -> None:
        env = {"AZURE_OPENAI_API_KEY": "key"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                api_client.check_environ_azure_openai()
            self.assertIn("AZURE_OPENAI_DEPLOYMENT_NAME", str(ctx.exception))
            self.assertIn("AZURE_OPENAI_ENDPOINT", str(ctx.exception))
            self.assertIn("OPENAI_API_VERSION", str(ctx.exception))
            self.assertNotIn("`AZURE_OPENAI_API_KEY`", str(ctx.exception))

    def test_check_environ_azure_openai_passes_when_all_set(self) -> None:
        env = {
            "AZURE_OPENAI_API_KEY": "key",
            "AZURE_OPENAI_DEPLOYMENT_NAME": "deployment",
            "AZURE_OPENAI_ENDPOINT": "https://example.com",
            "OPENAI_API_VERSION": "2024-01-01",
        }
        with patch.dict(os.environ, env, clear=True):
            api_client.check_environ_azure_openai()

    def test_embeddings_need_their_own_model_not_the_chat_one(self) -> None:
        env = {"OPENAI_API_KEY": "key", "OPENAI_MODEL": "gpt-test"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                api_client.check_environ_openai_embeddings()
            self.assertIn("OPENAI_EMBEDDING_MODEL", str(ctx.exception))
        env["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
        with patch.dict(os.environ, env, clear=True):
            api_client.check_environ_openai_embeddings()

    def test_check_environ_ollama_embeddings_raises_when_missing(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_MODEL": "llama3"}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                api_client.check_environ_ollama_embeddings()
            self.assertIn("OLLAMA_EMBEDDING_MODEL", str(ctx.exception))

    def test_check_environ_azure_openai_embeddings_names_the_deployment(self) -> None:
        env = {
            "AZURE_OPENAI_API_KEY": "key",
            "AZURE_OPENAI_DEPLOYMENT_NAME": "chat-deployment",
            "AZURE_OPENAI_ENDPOINT": "https://example.com",
            "OPENAI_API_VERSION": "2024-01-01",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                api_client.check_environ_azure_openai_embeddings()
            self.assertIn("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
