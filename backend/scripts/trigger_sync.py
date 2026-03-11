"""Trigger a manual sync."""
from backend.tasks.sync import sync_all_users
sync_all_users.delay()
print("Sync triggered!")
