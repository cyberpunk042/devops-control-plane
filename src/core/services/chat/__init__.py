"""
SCP Chat — embedded messaging for operations.

Public API:
    from src.core.services.chat import send_message, list_messages
    from src.core.services.chat import create_thread, list_threads
    from src.core.services.chat import push_chat, pull_chat
    from src.core.services.chat import encrypt_text, decrypt_text, is_encrypted
    from src.core.services.chat import parse_refs, resolve_ref, autocomplete
"""

from src.core.services.chat.chat_crypto import (
    decrypt_text,
    encrypt_text,
    is_encrypted,
)
from src.core.services.chat.chat_ops import (
    create_thread,
    delete_message,
    list_messages,
    list_threads,
    pull_chat,
    push_chat,
    send_message,
)
from src.core.services.chat.chat_refs import (
    autocomplete,
    parse_refs,
    resolve_ref,
)
from src.core.services.chat.models import (
    ChatMessage,
    MessageFlags,
    Thread,
)

__all__ = [
    "ChatMessage",
    "MessageFlags",
    "Thread",
    "autocomplete",
    "create_thread",
    "decrypt_text",
    "delete_message",
    "encrypt_text",
    "is_encrypted",
    "list_messages",
    "list_threads",
    "parse_refs",
    "pull_chat",
    "push_chat",
    "resolve_ref",
    "send_message",
]

