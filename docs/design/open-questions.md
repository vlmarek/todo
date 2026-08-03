# Open questions

Only genuinely unresolved behavior belongs here. Implementation must not choose
an answer silently.

## Report cursor boundary

Status: Open

Events exactly at the stored cursor are included. Confirm how duplicate events
are prevented across two finalized reports when the next interval begins at
the same timestamp.

## Comment modification history

Status: Open

Confirm whether Todoist supplies only the latest comment timestamp/content or
whether the report can distinguish an edit from a newly added comment.

## Moving dated work into a hidden category

Status: Open

Hidden-category tasks and steps cannot be dated. Decide whether moving a dated
task into such a category is rejected or requires an explicit clearing action.

## Deleted or renamed categories

Status: Open

Category behavior follows Todoist, but the CLI behavior when a configured
hidden category is renamed or deleted has not been specified.
