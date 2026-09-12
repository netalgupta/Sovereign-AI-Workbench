"""Attachment payload and backend state management package."""
from backend.attachments.manager import AttachmentManager, get_attachment_manager

__all__ = ["AttachmentManager", "get_attachment_manager"]
