"""Construct LangChain chat and embeddings clients for this monorepo's providers."""

import os
from collections.abc import Iterable
from typing import Any, Literal, overload

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import (
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
    ChatOpenAI,
    OpenAIEmbeddings,
)

from packages.common.logging_util import get_logger

LOGGER = get_logger(__name__)

Provider = Literal["azure", "ollama", "openai"]

_OPENAI_ENV_ALIASES = (
    ("LLM_ZSH_PYTHON_OPENAI_API_KEY", "OPENAI_API_KEY"),
    ("LLM_ZSH_PYTHON_OPENAI_MODEL", "OPENAI_MODEL"),
)


def _apply_openai_env_aliases() -> None:
    """Map the zsh-plugin env names onto the ones the OpenAI SDK reads.

    Only copies a variable that is actually set. Writing unconditionally
    replaced a perfectly good `OPENAI_API_KEY` with an empty string whenever the
    `LLM_ZSH_PYTHON_*` alias was absent.
    """
    for source, target in _OPENAI_ENV_ALIASES:
        value = os.getenv(source)
        if value:
            os.environ[target] = value


def _require_env_vars(
    names: Iterable[str],
    *,
    prefix: str = "Environment variable",
) -> None:
    missing = [name for name in names if not os.getenv(name)]

    if missing:
        formatted = ", ".join(f"`{name}`" for name in missing)
        raise ValueError(f"{prefix} {formatted} is not set.")


def check_environ_openai() -> None:
    """Check that the env vars the OpenAI chat client reads are set."""
    _require_env_vars(
        [
            "OPENAI_API_KEY",
            "OPENAI_MODEL",
        ]
    )


def check_environ_ollama() -> None:
    """Check that the env var the Ollama chat client reads is set."""
    _require_env_vars(["OLLAMA_MODEL"])


def check_environ_azure_openai() -> None:
    """Check that the env vars the Azure OpenAI chat client reads are set."""
    _require_env_vars(
        [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
            "AZURE_OPENAI_ENDPOINT",
            "OPENAI_API_VERSION",
        ]
    )


# An embeddings model is never the chat model, so each provider names its own.


def check_environ_openai_embeddings() -> None:
    """Check that the env vars the OpenAI embeddings client reads are set."""
    _require_env_vars(["OPENAI_API_KEY", "OPENAI_EMBEDDING_MODEL"])


def check_environ_ollama_embeddings() -> None:
    """Check that the env var the Ollama embeddings client reads is set."""
    _require_env_vars(["OLLAMA_EMBEDDING_MODEL"])


def check_environ_azure_openai_embeddings() -> None:
    """Check that the env vars the Azure OpenAI embeddings client reads are set."""
    _require_env_vars(
        [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
            "AZURE_OPENAI_ENDPOINT",
            "OPENAI_API_VERSION",
        ]
    )


@overload
def get_langchain_client(
    provider: Literal["azure"],
    **kwargs: Any,
) -> AzureChatOpenAI: ...


@overload
def get_langchain_client(
    provider: Literal["openai"],
    **kwargs: Any,
) -> ChatOpenAI: ...


@overload
def get_langchain_client(
    provider: Literal["ollama"],
    **kwargs: Any,
) -> ChatOllama: ...


def get_langchain_client(
    provider: Provider,
    **kwargs: Any,
) -> AzureChatOpenAI | ChatOpenAI | ChatOllama:
    """Build a chat client for `provider`, validating its environment first."""
    LOGGER.info("Creating LangChain client: provider=%s", provider)

    params: dict[str, Any] = {"verbose": True} | kwargs

    match provider:
        case "azure":
            check_environ_azure_openai()
            # The field is `deployment_name`, aliased `azure_deployment`.
            # Passing AZURE_OPENAI_DEPLOYMENT_NAME= instead made pydantic shunt
            # it into `model_kwargs`, so it went out as an API request-body
            # parameter while the deployment itself stayed unset.
            if not {"azure_deployment", "deployment_name"} & params.keys():
                params["azure_deployment"] = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
            return AzureChatOpenAI(**params)

        case "openai":
            _apply_openai_env_aliases()
            check_environ_openai()
            params.setdefault("model", os.environ["OPENAI_MODEL"])
            return ChatOpenAI(**params)

        case "ollama":
            # OLLAMA_MODEL is only the fallback; a caller that names the model
            # (e.g. from its own config file) doesn't need the env var set.
            if "model" not in params:
                check_environ_ollama()
                params["model"] = os.environ["OLLAMA_MODEL"]
            return ChatOllama(**params)


@overload
def get_embeddings_client(
    provider: Literal["azure"],
    **kwargs: Any,
) -> AzureOpenAIEmbeddings: ...


@overload
def get_embeddings_client(
    provider: Literal["openai"],
    **kwargs: Any,
) -> OpenAIEmbeddings: ...


@overload
def get_embeddings_client(
    provider: Literal["ollama"],
    **kwargs: Any,
) -> OllamaEmbeddings: ...


def get_embeddings_client(
    provider: Provider,
    **kwargs: Any,
) -> AzureOpenAIEmbeddings | OpenAIEmbeddings | OllamaEmbeddings:
    """Build an embeddings client for `provider`, validating its environment first.

    The model comes from its own variable -- OPENAI_EMBEDDING_MODEL,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT, OLLAMA_EMBEDDING_MODEL -- never the chat
    one, which can't embed.
    """
    LOGGER.info("Creating LangChain embeddings client: provider=%s", provider)

    params: dict[str, Any] = dict(kwargs)

    match provider:
        case "azure":
            check_environ_azure_openai_embeddings()
            # As for chat: the field is `deployment`, aliased `azure_deployment`.
            if not {"azure_deployment", "deployment"} & params.keys():
                params["azure_deployment"] = os.environ[
                    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
                ]
            return AzureOpenAIEmbeddings(**params)

        case "openai":
            _apply_openai_env_aliases()
            check_environ_openai_embeddings()
            params.setdefault("model", os.environ["OPENAI_EMBEDDING_MODEL"])
            return OpenAIEmbeddings(**params)

        case "ollama":
            check_environ_ollama_embeddings()
            params.setdefault("model", os.environ["OLLAMA_EMBEDDING_MODEL"])
            return OllamaEmbeddings(**params)
