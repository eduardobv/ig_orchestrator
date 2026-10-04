# Module: `gui/stories`

**Stories Inbox** — Move dumped story media files from a single input folder into each account's `story/` subfolder, identifying accounts by filename prefix.

## Purpose

After downloading stories via external tools (e.g., IG stogram, Telegram bot), they may be dumped into a single inbox folder with filenames like:

```
username1-20260904-123456.jpg
username2-20260904-654321.mp4
username1-20260904-789012.jpg
```

This module provides a dialog to move each file to the correct account folder, based on the username prefix and a lookup table in an external SQLite database (`accounts_dir` table).

## Files

- **`dialog.py`** — `StoriesInboxMixin` class providing `_open_stories_inbox()` method
- **`settings.py`** — Load/save inbox and DB paths from `app_settings` table

## Responsibility

The module is responsible for:

1. **UI Dialog**: Modal window (Toplevel) with:
   - Input field for inbox folder path (+ Browse button)
   - Input field for accounts DB path (+ Browse button)
   - Text log area for results
   - Save, Run, and Close buttons

2. **Storage**: Persist paths in `app_settings`:
   - `stories.inbox_path` → folder with story files
   - `stories.accounts_db_path` → external SQLite DB with `accounts_dir` table

3. **Execution**: Call `organize_story_inbox()` from `filesystem/story_inbox.py`

## Integration

- Mixin is added to `shell/app.py`'s `InstagramOrchestratorApp` class
- Menu entry in **Batch** menu (`menu.batch.stories`)
- Connection instance passed to mixin (used for app_settings)
- `self.root` (Tk root window) used for parent of dialog and file dialogs

## Flow

1. User clicks **Batch → Organize Stories**
2. `_open_stories_inbox()` creates modal window
3. Modal loads saved paths from `app_settings`
4. User may edit paths and click **Save** (persists to app_settings)
5. User clicks **Run**:
   - Validates paths not empty
   - Calls `organize_story_inbox()` with inbox + DB paths
   - Writes results to text log
   - Disables/enables Run button while processing

## Error Handling

- **Paths empty**: Show error, prompt user
- **StoryInboxError** (invalid paths, DB missing tables): Show error dialog
- **Generic exception**: Show error dialog
- **File not found in accounts_dir**: Log as `USERNAME_NOT_IN_DB`
- **Destination already exists**: Log as `DESTINATION_EXISTS`

## Translations

Required i18n keys (see `shared/locales/es.json` and `en.json`):

- `stories.title` — Modal title
- `stories.inbox` — Label for inbox path field
- `stories.db` — Label for DB path field
- `stories.browse` — Text for Browse buttons
- `stories.log` — Label for log area
- `stories.save` — Save button
- `stories.run` — Run button
- `stories.close` — Close button
- `stories.saved` — Status message when paths saved
- `stories.paths_required` — Error when paths are empty
- `stories.summary` — Summary line with moved/errors/total counts

## External Dependencies

- **`filesystem/story_inbox.py`** — Logic to move files
- **`gui/text_edit.py`** — `bind_edit_context_menu()`
- **`gui/shared/helpers.py`** — `_gui_setting()` (for reading app_settings)
- **`gui/stories/settings.py`** — Load/save functions

## Testing

- `tests/gui/test_stories_dialog.py` — Verify modal opens/closes, paths load/save
- `tests/filesystem/test_story_inbox.py` — Test move logic with mock files/DB
