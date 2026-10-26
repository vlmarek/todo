"""Pure rendered documents and optional external delivery; see API.md."""
from .formatting import (Color, edge, absolute, compact, actual_due, ancestor_path,
                         owner_title, waiting_reason, timing, time_block)
from .render import (Document, document, render_now, render_detail, render_comments,
                     render_categories, render_waiting, render_someday, render_search,
                     render_ambiguity, invalid_selection, history_warning,
                     pagination_progress, render_report_cursor)
from .report import ReportEvent, render_report
from .receipts import (CommentOutcome, render_mutation, render_move,
                       render_created_category, render_comment_bodies, render_comment_edit,
                       render_receipts)
from .delivery import OriginalStreams, OutputError, deliver
