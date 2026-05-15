# Recovery Apply Order

If PR conflicts were accidentally applied out-of-order, use the latest branch state as source-of-truth and re-apply in commit order.

## Canonical drive modes
- ECO
- NORMAL
- SPORT
- RACE
- ALBATROSS

## Notes
- `renderer.py` and `ui_utils.py` are sensitive to partial merges.
- If conflicts appear in these files, prefer incoming changes from the newest recovery PR.
